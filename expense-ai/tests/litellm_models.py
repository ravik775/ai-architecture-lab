
import tkinter as tk
from tkinter import ttk
import litellm

PROVIDER_BASE_URLS={
 "openai":"https://api.openai.com/v1",
 "github":"https://models.github.ai/inference",
 "openrouter":"https://openrouter.ai/api/v1",
 "groq":"https://api.groq.com/openai/v1",
 "ollama":"http://localhost:11434",
 "gemini":"https://generativelanguage.googleapis.com",
 "anthropic":"https://api.anthropic.com",
 "cohere":"https://api.cohere.ai",
 "mistral":"https://api.mistral.ai/v1",
 "together_ai":"https://api.together.xyz/v1",
 "fireworks_ai":"https://api.fireworks.ai/inference/v1",
 "deepinfra":"https://api.deepinfra.com/v1/openai",
 "perplexity":"https://api.perplexity.ai"
}

def build():
    p={}
    for m,i in litellm.model_cost.items():
        prov=i.get("litellm_provider") or i.get("provider") or "unknown"
        p.setdefault(prov,[]).append((m,i))
    return p

providers=build()
root=tk.Tk()
root.title("LiteLLM Model Explorer")
root.geometry("1650x850")

top=ttk.Frame(root,padding=8); top.pack(fill="x")
ttk.Label(top,text="Provider").pack(side="left")
provider=tk.StringVar()
combo=ttk.Combobox(top,textvariable=provider,state="readonly",values=sorted(providers),width=25)
combo.pack(side="left",padx=5)
ttk.Label(top,text="Search").pack(side="left",padx=(15,5))
search=tk.StringVar()
ttk.Entry(top,textvariable=search,width=30).pack(side="left")

cols=("Model","Provider","Base URL","Input Cost","Output Cost","Free")
tree=ttk.Treeview(root,columns=cols,show="headings")
for c,w in [("Model",520),("Provider",120),("Base URL",320),("Input Cost",100),("Output Cost",100),("Free",70)]:
    tree.heading(c,text=c); tree.column(c,width=w)
tree.pack(side="left",fill="both",expand=True,padx=8,pady=8)
scr=ttk.Scrollbar(root,orient="vertical",command=tree.yview)
tree.configure(yscrollcommand=scr.set); scr.pack(side="left",fill="y")

right=ttk.Frame(root,padding=8); right.pack(side="right",fill="y")
fields={}
for n in ["Model","Provider","Base URL","Context","Max Output","Input Cost","Output Cost","Free"]:
    ttk.Label(right,text=n).pack(anchor="w")
    e=ttk.Entry(right,width=55); e.pack(fill="x",pady=2); fields[n]=e

status=ttk.Label(root,relief="sunken",anchor="w"); status.pack(side="bottom",fill="x")

def sel():
    s=tree.selection()
    return tree.item(s[0])["values"] if s else None

def clip(txt,msg):
    root.clipboard_clear(); root.clipboard_append(txt); root.update()
    status.config(text=msg)

def details(*_):
    v=sel()
    if not v:return
    info=litellm.model_cost.get(v[0],{})
    data={"Model":v[0],"Provider":v[1],"Base URL":v[2],"Context":info.get("max_input_tokens",""),
    "Max Output":info.get("max_output_tokens",""),"Input Cost":v[3],"Output Cost":v[4],"Free":v[5]}
    for k,e in fields.items():
        e.config(state="normal"); e.delete(0,"end"); e.insert(0,str(data[k])); e.config(state="readonly")

def refresh(*_):
    tree.delete(*tree.get_children())
    q=search.get().lower()
    c=0
    for m,i in sorted(providers.get(provider.get(),[])):
        if q and q not in m.lower(): continue
        ic=i.get("input_cost_per_token",0); oc=i.get("output_cost_per_token",0)
        tree.insert("",tk.END,values=(m,provider.get(),PROVIDER_BASE_URLS.get(provider.get(),"Configured by user"),ic,oc,"Yes" if ic==0 and oc==0 else "No"))
        c+=1
    status.config(text=f"{c} models")

def copy_model():
    v=sel()
    if v: clip(v[0],"Copied model")

def copy_url():
    v=sel()
    if v: clip(v[2],"Copied URL")

def copy_both():
    v=sel()
    if v: clip(f"model={v[0]}\nbase_url={v[2]}","Copied both")

def copy_snippet():
    v=sel()
    if not v:return
    txt=f'''from litellm import completion

completion(
    model="{v[0]}",
    api_base="{v[2]}",
    api_key="YOUR_API_KEY",
    messages=[{{"role":"user","content":"Hello"}}]
)
'''
    clip(txt,"Copied snippet")

def copy_curl():
    v=sel()
    if not v:return
    txt=f'curl {v[2]}/chat/completions -H "Authorization: Bearer YOUR_API_KEY"'
    clip(txt,"Copied curl")

for t,cmd in [("Copy Model",copy_model),("Copy URL",copy_url),("Copy Both",copy_both),("Copy LiteLLM",copy_snippet),("Copy curl",copy_curl)]:
    ttk.Button(right,text=t,command=cmd).pack(fill="x",pady=2)

combo.bind("<<ComboboxSelected>>",refresh)
search.trace_add("write",refresh)
tree.bind("<<TreeviewSelect>>",details)
tree.bind("<Double-1>",lambda e:copy_model())
root.bind("<Control-c>",lambda e:copy_model())
root.bind("<Control-l>",lambda e:copy_snippet())

combo.current(0)
refresh()
root.mainloop()

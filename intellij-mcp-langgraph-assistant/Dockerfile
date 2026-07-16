FROM python:3.12

WORKDIR /app

COPY requirements.txt .

RUN pip install -r requirements.txt

COPY app .

RUN echo "Current directory:"
RUN pwd

RUN echo "Files in /app:"
RUN ls -la /app

CMD ["python", "main.py"]
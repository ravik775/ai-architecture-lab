import re
import importlib.metadata


def get_clean_package_name(line):
    # Remove comments and whitespace
    line = line.split('#')[0].strip()
    if not line or line.startswith('-r'):
        return None

    # Remove extra brackets/extras (e.g., python-jose[cryptography] -> python-jose)
    name = re.split(r'[<=>\[\s]', line)[0]
    return name.strip()


def check_requirements(filename="requirements.txt"):
    try:
        with open(filename, "r") as f:
            lines = f.readlines()
    except FileNotFoundError:
        print(f"Error: Could not find '{filename}' in the current directory.")
        return

    print(f"{'PACKAGE':<40} | {'INSTALLED VERSION':<20}")
    print("-" * 65)
    packages = []
    for line in lines:
        pkg_name = get_clean_package_name(line)
        if not pkg_name:
            continue

        try:
            # Fetch the installed version using modern importlib.metadata
            installed_version = importlib.metadata.version(pkg_name)
            packages.append(f"{pkg_name}=={installed_version}")
        except importlib.metadata.PackageNotFoundError:
            print(f"{pkg_name:<40} | {'NOT INSTALLED':<20}")
    print("\n".join(sorted(set(packages))))

if __name__ == "__main__":
    check_requirements()
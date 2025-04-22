def normalize_path(path):
    path = path.strip().strip("'\"` ")

    # Normalize Flask-style <param> and JS-style ${param} to :var
    path = re.sub(r"<[^>]+>", ":var", path) # Replace Flask-style <param> with :var
    path = re.sub(r"\$\{[^}]+\}", ":var", path) # Replace JS-style ${param} with :var

    
    path = re.sub(r"\s*\+\s*\w+", "", path) # Remove + variable concat artifacts

    # Normalize slashes
    path = re.sub(r"//+", "/", path)
    return path.rstrip("/") + "/"

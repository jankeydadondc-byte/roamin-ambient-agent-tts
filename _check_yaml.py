import yaml

with open(".pre-commit-config.yaml") as f:
    yaml.safe_load(f.read())
print("YAML OK")

modules = ["python-3.11"]

[nix]
channel = "stable-24_05"

[workflows]
runButton = "Start Application"

[[workflows.workflow]]
name = "Start Application"
author = "you"

[[workflows.workflow.tasks]]
task = "packager.installForAll"

[[workflows.workflow.tasks]]
task = "shell.exec"
args = "gunicorn --bind 0.0.0.0:5000 app:app --log-level warning"
waitForPort = 5000

[[ports]]
localPort = 5000
externalPort = 80

[env]
LOGLEVEL = "warning"






run = "gunicorn --bind 0.0.0.0:5000 app:app"

modules = ["python-3.11"]

[nix]
channel = "stable-24_05"

[[ports]]
localPort = 5000
externalPort = 80

[env]
LOGLEVEL = "warning"

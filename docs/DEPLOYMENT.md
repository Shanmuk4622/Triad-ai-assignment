# Setup and deployment

## Windows options

Docker Compose is the shortest setup because it includes the database and Tesseract. If `docker` is missing from PowerShell after launching Docker Desktop, try the installed per-user CLI from this project folder:

```powershell
$dockerExe = Join-Path $env:LOCALAPPDATA 'Programs\DockerDesktop\resources\bin\docker.exe'
& $dockerExe compose up --build --wait
```

For a native Python run, start a local MongoDB service, or run a standalone database container on loopback. The command below is for a native app talking to a database container:

```powershell
docker run -d --name triad-mongo -p 127.0.0.1:27017:27017 -v triad-native-data:/data/db mongo:8.0-noble
```

Install Tesseract with English data and put `tesseract.exe` on `PATH`, or set `TESSERACT_CMD` to its full path. In PowerShell, verify `tesseract --list-langs` includes `eng`.

Use your `cv_conda` environment, or create a plain Python virtual environment. With either environment active:

```powershell
python -m pip install -r requirements.txt
$env:MONGO_URI = 'mongodb://127.0.0.1:27017'
python -m flask --app dms run --host 127.0.0.1 --port 7860
```

To use the Conda interpreter directly without activation, replace `python` in those commands with `& 'C:\Users\shanm\dev\envs\cv_conda\python.exe'`. Run `python -m flask --app dms make-admin alice` in the same environment to promote a registered account.

## GitHub

The assignment repository is [Shanmuk4622/Triad-ai-assignment](https://github.com/Shanmuk4622/Triad-ai-assignment). Inspect its branch before the first push with `git fetch origin` and `git log --all --oneline`. If it is empty, run `git push -u origin main`. If it has an existing branch, integrate the remote history and resolve any overlapping files before pushing.

Stage project files explicitly and check `git diff --cached` before committing. `.env`, the private assignment PDF, generated reports, and data directories are ignored. Commit features as working milestones. The README is the submission entry point.

### Import the bundled commits

If you received `triad-dms-history.bundle` alongside the project and `git status` says **No commits yet**, run these commands in regular PowerShell from the project folder. The mixed reset imports the commit history and leaves the saved working files in place.

```powershell
git bundle verify .\triad-dms-history.bundle
git fetch .\triad-dms-history.bundle main
git reset --mixed FETCH_HEAD
git log --oneline -4
```

Use the GitHub commands above after importing the history. You can also clone the bundle into a new folder with `git clone .\triad-dms-history.bundle triad-dms` and set `origin` to your GitHub URL.

## Hugging Face Space

The root README has the configuration for a Docker Space on port `7860`. The same image runs MongoDB on an internal loopback address when no `MONGO_URI` is set. This supports a self-contained demo because Hugging Face restricts outbound ports, which can block a direct connection to a standard remote MongoDB port. The built-in database uses the Space’s container disk. Treat it as disposable and use sample documents. [Docker Spaces](https://huggingface.co/docs/hub/spaces-sdks-docker) · [Space networking](https://huggingface.co/docs/hub/en/spaces-overview#networking) · [Disk usage](https://huggingface.co/docs/hub/spaces-storage)

1. Identify the existing Space in your Hugging Face account. Use that repository to replace its previous app files while keeping its URL and commit history. If choosing a new Space, select the Docker SDK.
2. In Space **Settings**, set a strong `SECRET_KEY` as a secret. To create an admin at startup, set `DMS_ADMIN_PASSWORD` as a secret of at least 12 characters and `DMS_ADMIN_USERNAME` as a variable. Optionally set `DMS_ADMIN_DIVISION`, which defaults to `Division A`. These variables seed the account on a fresh database. An existing registered account with the same username must be promoted through the CLI first.
3. Keep `HF_TOKEN` in the local `.env` and use it for the deployment CLI. Export only the committed source files with `git archive`. Review the exact Space name and its Files tab before replacing the root contents.

```powershell
python -m pip install -U huggingface_hub
$tokenLine = Get-Content -LiteralPath .env | Where-Object { $_ -match '^\s*HF_TOKEN\s*=' } | Select-Object -First 1
$env:HF_TOKEN = ($tokenLine -split '=', 2)[1].Trim().Trim('"').Trim("'")
hf auth whoami
$spaceId = 'YOUR_ACCOUNT/YOUR_SPACE'
$export = Join-Path $env:TEMP ('triad-space-' + [guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $export | Out-Null
git archive --format=zip --output="$export.zip" HEAD
Expand-Archive -LiteralPath "$export.zip" -DestinationPath $export
hf upload $spaceId $export . --repo-type space --delete '*' --commit-message 'Deploy TRIAD document management system'
Remove-Item Env:HF_TOKEN
```

Use the delete pattern only for a Space whose old files are being replaced. After the build finishes, open the Space app, check `/api/health` on the app’s `hf.space` URL, and repeat the walkthrough in [TESTING.md](TESTING.md). For a persistent hosted database, use a `MONGO_URI` that is reachable from the Space over its allowed network ports.

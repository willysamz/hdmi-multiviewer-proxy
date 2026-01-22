# Repository Setup

After creating the GitHub repository, complete these one-time setup steps:

## 1. Create gh-pages Branch

The Helm chart is hosted on GitHub Pages. Create the initial branch:

```bash
# Create orphan gh-pages branch
git checkout --orphan gh-pages
git rm -rf .

# Create initial index
echo "# MViewer Proxy Helm Charts" > README.md
touch index.yaml

git add README.md index.yaml
git commit -m "Initialize gh-pages for Helm chart hosting"
git push origin gh-pages

# Return to main branch
git checkout main
```

## 2. Enable GitHub Pages

1. Go to repository **Settings** → **Pages**
2. Source: **Deploy from a branch**
3. Branch: **gh-pages** / **(root)**
4. Save

## 3. Configure Package Visibility

The container image is published to GitHub Container Registry (ghcr.io).

1. After the first image is pushed, go to the package settings
2. Change visibility to **Public** if desired
3. Link the package to the repository for better discoverability

## 4. Create First Release

```bash
git tag v0.1.0
git push origin v0.1.0
```

This will trigger the release workflow which:
- Runs tests
- Builds and pushes multi-arch Docker image (amd64, arm64)
- Packages and publishes the Helm chart

## Usage After Setup

### Docker Image

```bash
docker pull ghcr.io/wsamuels/hdmi-multiviewer-proxy:latest
docker pull ghcr.io/wsamuels/hdmi-multiviewer-proxy:0.1.0
```

### Helm Chart

```bash
helm repo add hdmi-multiviewer-proxy https://wsamuels.github.io/hdmi-multiviewer-proxy
helm repo update
helm install mviewer hdmi-multiviewer-proxy/hdmi-multiviewer-proxy
```

# TellStick Local — Dev Channel

> ⚠️ **This is the development channel.** Builds here track the `dev` branch
> of [addon-tellstick-local](https://github.com/R00S/addon-tellstick-local) and
> may be unstable. For stable releases use that repo instead.

## What this repo is

This is a thin HAOS app repository that points at the `:dev` Docker images
built from the `dev` branch of the main code repository. It contains no code
of its own — only the `repository.json` and `tellsticklive/config.yaml` needed
for the HAOS Supervisor to locate and install the dev image.

The Docker images are built automatically by the `edge.yaml` workflow in
[addon-tellstick-local](https://github.com/R00S/addon-tellstick-local/actions/workflows/edge.yaml)
on every push to the `dev` branch.

## How to install the dev channel

1. In HAOS go to **Settings → Apps → ⋮ → Repositories**
2. Add: `https://github.com/R00S/addon-tellstick-local-dev`, category **App**
3. Find **TellStick Local (Dev)** in the app store and click **Install**

The app slug is `tellsticklive-dev` so it can coexist with the stable version.

## Development workflow

```
feature branch  →  dev branch  →  main branch
                      ↓               ↓
                  edge.yaml       deploy.yaml
                  builds :dev     builds :X.Y.Z
                  images          images
                      ↓
              addon-tellstick-local-dev
              (this repo — always :dev)
```

1. Work on a feature branch in `addon-tellstick-local`
2. Merge into the `dev` branch when ready for wider testing
3. The `edge.yaml` workflow automatically rebuilds the `:dev` Docker image
4. Testers who have added this dev channel repo get the update on next app restart
5. When the feature is stable, open a PR from `dev` → `main` in `addon-tellstick-local`
6. On merge to `main`, create a GitHub release — `deploy.yaml` builds and
   publishes the versioned stable images

## Support

- [Open an issue on GitHub](https://github.com/R00S/addon-tellstick-local/issues)

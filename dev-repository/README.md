# TellStick Local — Dev Channel (addon-tellsticklive-roosfork)

> ⚠️ **This is the development channel.** Builds here track the `dev` branch
> of [addon-tellstick-local](https://github.com/R00S/addon-tellstick-local) and
> may be unstable.

## For existing users — you are now on the dev channel

If you had `https://github.com/R00S/addon-tellsticklive-roosfork` added to your
HAOS, you are already here. **You will continue to receive updates automatically**
— nothing is broken. However, you are now on the **development channel**, which
may occasionally be unstable.

### How to switch to the stable channel

1. In HAOS go to **Settings → Apps → ⋮ → Repositories**
2. Remove `https://github.com/R00S/addon-tellsticklive-roosfork`
3. Add `https://github.com/R00S/addon-tellstick-local`, category **App**
4. Find **TellStick Local** in the app store — your existing configuration is
   preserved (same slug `tellsticklive`, same data directory)

## What this repo is

This is the dev/edge channel for TellStick Local. It is a thin HAOS app
repository that points at the `:dev` Docker images built automatically from the
`dev` branch of [addon-tellstick-local](https://github.com/R00S/addon-tellstick-local).
It contains no code of its own — only the `repository.json` and
`tellsticklive/config.yaml` needed for the HAOS Supervisor to locate and pull
the dev image.

The Docker images are rebuilt by the `edge.yaml` workflow in
[addon-tellstick-local](https://github.com/R00S/addon-tellstick-local/actions/workflows/edge.yaml)
on every push to the `dev` branch.

## Why the old repo URL is used here

This repository lives at `https://github.com/R00S/addon-tellsticklive-roosfork`
(the original repository path). This is intentional: existing users who had
already added that URL to HAOS continue to receive automatic updates without
any manual action on their part. Without this, they would be orphaned on the
last release and never receive further updates.

## Development workflow

```
feature branch  →  dev branch  →  main branch
                      ↓               ↓
                  edge.yaml       deploy.yaml
                  builds :dev     builds :X.Y.Z
                  images          images
                      ↓
          addon-tellsticklive-roosfork  (this repo)
          (existing users auto-update on every restart)
```

1. Work on a feature branch in `addon-tellstick-local`
2. Merge into the `dev` branch when ready for wider testing
3. `edge.yaml` automatically rebuilds the `:dev` Docker image
4. Dev channel users get the update on next app restart
5. When stable, open a PR from `dev` → `main` in `addon-tellstick-local`
6. On merge to `main`, create a GitHub release — `deploy.yaml` builds the
   versioned stable images for the stable channel

## Support

- [Open an issue on GitHub](https://github.com/R00S/addon-tellstick-local/issues)

# Receiver images from this fork

This fork adds AAC bitrate and receiver counters from upstream PR #2305.
It follows the upstream `development` branch and currently builds Shairport Sync `5.6-dev`.
The image includes NQPTP from its `development` branch with a matching shared-memory interface.
Each initial image build refreshes the NQPTP stage so it fetches current upstream code.
Other build stages retain their cache.
It supports both Classic AirPlay and AirPlay 2 with the upstream startup script.

GitHub Actions builds and tests images for Linux AMD64 and ARM64.
Each architecture builds on a native GitHub-hosted runner.
The workflow compiles Classic AirPlay and AirPlay 2 with metadata enabled and disabled.
These are four compile configurations. The published Docker image includes metadata support.
Both image builds run `make check` and test receiver startup in both modes.
Before publishing the combined manifest, each native runner downloads and tests its pushed image by digest.
The tests also make sure that the receiver and NQPTP use the same shared-memory interface.

The registry is `ghcr.io/leonroy/shairport-sync`.
Each publishing run retains its architecture build tags and publishes a `sha-<full-commit-sha>` image after testing.
An existing commit tag cannot change to different runtime images.
Successful image jobs pass their tested digest references to the publishing job.
Rerunning only the publishing job reuses those references even when its run attempt changes.
The Actions summary contains the commit tag and manifest digest.
A manifest digest identifies one set of images.

On a push to `development`, the workflow promotes the tested image to `development` and `latest`.
Before promotion, it makes sure that the source commit still matches the head of `development`.
A merge into `development` triggers the same workflow as a push.
A push or merge to `master` does not publish an image to GHCR.
The `latest` tag in this fork follows tested `development` code.
The `build/telemetry-ghcr` branch publishes commit images for review without changing `latest`.
Pull request runs build and test images without publishing.
The inherited Docker Hub workflow skips this fork, which uses GHCR instead.
Other upstream build workflows remain enabled.

The AAC bitrate and receiver counters use the existing metadata controls from Shairport Sync.
Upstream PR #2305 adds no separate flag for these measurements.
The code requires metadata support at build time through flags such as `--with-metadata` and `--with-metadata-pipe`.
At runtime, metadata is enabled by default when the build includes it.
Set `metadata.enabled = "no"` in the configuration file to stop metadata reports, including these measurements.
The existing `-M` or `--metadata-enable` command-line flag enables metadata.

The workflow uses `GITHUB_TOKEN` with package write permission.
No Docker Hub credentials or additional registry secret are required.
After the first publish, open the package settings on GitHub and change its visibility to Public.
Make sure that a Docker client without GHCR credentials can pull the image.
Public visibility permits downloads and does not grant push access.

The bridge uses `ghcr.io/leonroy/shairport-sync:latest` in its Compose file.
To update the receiver, run these commands on its Docker host:

```sh
docker compose pull shairport-sync
docker compose up -d shairport-sync
```

Disconnect and reconnect AirPlay after replacing the receiver.
To select an earlier image, replace the receiver image in Compose with a recorded commit tag or manifest digest.
Then run the same commands on the Docker host.
Merge future upstream development updates into this fork to retain the original telemetry commit history.

## AGPL Compliance Notes

This file is a practical checklist for this repository.
It is not legal advice.

### What Is Already Present In This Repository

The following project-level items are already present for license transparency:

- `LICENSE` contains the GNU Affero General Public License v3.0 text
- `NOTICE.md` identifies this repository as a modified version of the upstream project
- `README.md` points readers to the license and upstream project
- package metadata in `package.json` and `backend/pyproject.toml` declares `AGPL-3.0`

### What You Must Keep When Sharing This Repository

If you copy, redistribute, or publish this repository, keep:

- `LICENSE`
- `NOTICE.md`
- existing copyright notices
- attribution to the upstream project

### If You Modify The Project Further

If you change the code again, you should:

- state that your version is modified
- update `NOTICE.md` with a short summary of the new changes
- keep the AGPL license text with the project

### If You Distribute Builds, Docker Images, Or Bundles

If you distribute a built or packaged version of this project, make sure recipients can also access the corresponding source code for that same version.

In practice, that usually means:

- distribute the source together with the build, or
- provide a clear and durable link to the exact corresponding source

### If You Run It As A Public Network Service

The AGPL has an extra requirement for software used over a network.

If users interact with your modified version through a browser, app, or API over a network, you should provide those users with access to the corresponding source code of the version that is actually running.

For this repository, the safest deployment practice is:

- add a visible `Source Code` link in the UI or deployment landing page
- point that link to the exact repository or archive for the running version
- keep the link available to remote users for as long as that version is running

### Third-Party Dependencies

The AGPL status of this repository does not replace third-party license obligations.

You should separately review the licenses for:

- Node dependencies
- Python dependencies
- container images
- model providers and external services

### Upstream Project

Original project:

- [github.com/666ghj/MiroFish](https://github.com/666ghj/MiroFish)

# Antenna Observatory documentation

This shared site publishes the Antenna Observatory documentation from the [Antenna Observatory source repository](https://github.com/ramideltoro/antenna_observatory/tree/main/wiki-site) and the Skyglow section from the [Skyglow source repository](https://github.com/ramideltoro/skyglow/tree/main/wiki/skyglow). Each application synchronizes its canonical pages and release record only after a successful production deployment.

The published documentation is available at <https://docs.ramideltoro.com>.

To preview it locally:

```bash
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
mkdocs serve
```

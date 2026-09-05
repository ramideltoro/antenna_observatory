# Antenna Observatory documentation

This site publishes the Antenna Observatory documentation from the [Antenna Observatory source repository](https://github.com/ramideltoro/antenna_observatory/tree/main/wiki-site). A successful production deployment synchronizes these canonical pages and the release record to the standalone wiki repository.

The published documentation is available at <https://wiki.antenna.ramideltoro.com>. Documentation for the related multi-band receiver is maintained independently at the [Skyglow wiki](https://wiki.skyglow.ramideltoro.com).

To preview it locally:

```bash
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
mkdocs serve
```

# Updating Pipeline References

The project bibliography is maintained in the NASA SciX (formerly NASA/ADS) public library:

<https://scixplorer.org/public-libraries/w9Eg1EwtTAK14nz2CuQ2Fg>  
*(Legacy ADS URL: <https://ui.adsabs.harvard.edu/public-libraries/w9Eg1EwtTAK14nz2CuQ2Fg>)*

*(Contact RX if you need collaborator edit access on SciX/ADS.)*

## Option A: Automated Update via Pixi (Recommended)

1. Save your NASA SciX / ADS API Token (free from [SciX API Token Settings](https://scixplorer.org/user/settings/token) or [ADS Settings](https://ui.adsabs.harvard.edu/user/settings/token)) into a private file:

   ```bash
   mkdir -p ~/.scix
   echo "your-scix-api-token" > ~/.scix/token
   chmod 600 ~/.scix/token
   ```

   *(Legacy `~/.ads/dev_key` and environment variables `export SCIX_API_TOKEN="your-token"` or `export ADS_DEV_KEY="your-token"` are also supported.)*

2. Run the update task:

   ```bash
   pixi run update-references
   ```

Or run the script directly:

```bash
python scripts/update_references.py
```

## Option B: Manual Export

1. Open the [NASA SciX Library](https://scixplorer.org/public-libraries/w9Eg1EwtTAK14nz2CuQ2Fg) (or [ADS Library](https://ui.adsabs.harvard.edu/public-libraries/w9Eg1EwtTAK14nz2CuQ2Fg)).
2. Select **Export** $\rightarrow$ **BibTeX ABS**.
3. Save/overwrite `docs/source/references/pipeline.bib`.

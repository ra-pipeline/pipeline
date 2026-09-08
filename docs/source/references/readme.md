# Updating Pipeline References

The project bibliography is maintained in the NASA/ADS public library:

<https://ui.adsabs.harvard.edu/public-libraries/w9Eg1EwtTAK14nz2CuQ2Fg>

*(Contact RX if you need collaborator edit access on ADS.)*

## Option A: Automated Update via Pixi (Recommended)

1. Save your NASA/ADS API Token (free from [ADS API Token Settings](https://ui.adsabs.harvard.edu/user/settings/token)) into a private file:

   ```bash
   mkdir -p ~/.ads
   echo "your-ads-api-token" > ~/.ads/dev_key
   chmod 600 ~/.ads/dev_key
   ```

   *(Alternatively: `export ADS_DEV_KEY="your-ads-token"`, though not recommended for security reasons.)*

2. Run the update task:

   ```bash
   pixi run update-references
   ```

Or run the script directly:

```bash
python scripts/update_references.py
```

## Option B: Manual Export

1. Open the [NASA/ADS Library](https://ui.adsabs.harvard.edu/public-libraries/w9Eg1EwtTAK14nz2CuQ2Fg).
2. Select **Export** $\rightarrow$ **BibTeX ABS**.
3. Save/overwrite `docs/source/references/pipeline.bib`.

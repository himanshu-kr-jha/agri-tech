exec(open("_gen.py").read().split("# ---------------------------------------------------------------- 01 title")[0])

def arrow():
    return '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="#899A8C" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><path d="M5 12h14M13 6l6 6-6 6"/></svg>'

# ---------------------------------------------------------------- 03 pipeline
steps = [
 ("Registry", "One file declares every source: publisher, access route, licence, cadence, tier.", "No URL is hardcoded anywhere else."),
 ("Fetch", "Official API first. Plain HTTP. Never a workaround.", "Retries with backoff; a failure keeps the last good copy."),
 ("Manifest", "Publisher, retrieval date and a SHA-256 per file.", "A later re-fetch can be proved identical."),
 ("Cadence", "Each domain re-checks on its own clock.", "MSP 90 days · costs 365 · schemes 90 · prices daily."),
]
inner = '''  <div style="padding: 34px 0 30px; display: flex; justify-content: space-between; align-items: flex-end;">
    <div class="serif" style="font-size: 46px;">How the data is collected</div>
    <div class="body" style="font-size: 14px; max-width: 380px; text-align: right;">Built to be re-run, not run once. Government data changes; a seed that was true in August is not automatically true in March.</div>
  </div>
  <div style="display: flex; align-items: stretch; gap: 20px; flex-grow: 1;">
'''
for i, (t, d, n) in enumerate(steps):
    inner += f'''    <div style="flex-grow: 1; flex-basis: 0; display: flex; flex-direction: column; gap: 12px; padding: 26px 24px; border: 1px solid rgba(221,227,223,0.7); background: #FFFFFF;">
      <span class="eyebrow mono">0{i+1}</span>
      <span class="serif" style="font-size: 27px;">{t}</span>
      <span class="body" style="font-size: 14px; flex-grow: 1;">{d}</span>
      <span class="body" style="font-size: 13px; padding-top: 12px; border-top: 1px solid rgba(221,227,223,0.7);">{n}</span>
    </div>
'''
    if i < len(steps) - 1:
        inner += f'    <div style="display: flex; align-items: center;">{arrow()}</div>\n'
inner += '''  </div>
  <div style="margin-top: 26px; padding: 20px 24px; border-left: 2px solid #C7A03D; background: #FFFFFF;">
    <span style="font-size: 15px; color: #1B221F;">A re-run that finds nothing changed costs <span class="serif" style="font-size: 19px;">1.2 seconds</span> and writes nothing. Only a genuine change updates the record of <span style="font-style: italic;">when this last changed</span>.</span>
  </div>
'''
write("Pipeline.dc.html", "How we collect", "03", inner)

# ---------------------------------------------------------------- 04 sources
src = [
 ("01", "Minimum Support Price", "CACP / DES", "23 crops, current to 2025-26", "Authoritative"),
 ("02", "Cost of production", "DES", "State × crop, 2013-14 to 2017-18", "Authoritative"),
 ("03", "UP schemes &amp; orders", "Govt of Uttar Pradesh", "Hindi, current to Aug 2026", "Authoritative"),
 ("04", "Crop varieties", "ICAR", "255 released varieties", "Authoritative"),
 ("05", "Production, area, yield", "Ministry of Agriculture", "33,306 UP rows, district level", "Authoritative"),
 ("06", "Procurement", "DFPD / FCI", "Quantity, MSP value, farmers benefited", "Authoritative"),
 ("07", "Department circulars &amp; FAQs", "Govt of Uttar Pradesh", "69 circulars, bilingual", "Advisory"),
]
inner = '''  <div style="padding: 34px 0 26px; display: flex; justify-content: space-between; align-items: flex-end;">
    <div class="serif" style="font-size: 46px;">Where it comes from</div>
    <div class="body" style="font-size: 14px;">Every source is a government publisher. No blogs, no aggregators, no scraped resellers.</div>
  </div>
  <div style="display: grid; grid-template-columns: 46px 1fr 1fr 1.15fr 132px; gap: 0 22px; align-items: center; padding-bottom: 11px; border-bottom: 1px solid rgba(221,227,223,0.7);">
    <span class="eyebrow"></span><span class="eyebrow">Domain</span><span class="eyebrow">Publisher</span><span class="eyebrow">Coverage</span><span class="eyebrow" style="text-align: right;">Tier</span>
  </div>
'''
for n, dom, pub, cov, tier in src:
    gold = "#C7A03D" if tier == "Advisory" else "#899A8C"
    inner += f'''  <div style="display: grid; grid-template-columns: 46px 1fr 1fr 1.15fr 132px; gap: 0 22px; align-items: center; padding: 15px 0; border-bottom: 1px solid rgba(221,227,223,0.7);">
    <span class="eyebrow mono">{n}</span>
    <span style="font-size: 16px; color: #1B221F; font-weight: 500;">{dom}</span>
    <span class="body" style="font-size: 14px;">{pub}</span>
    <span class="body" style="font-size: 14px;">{cov}</span>
    <span class="mono" style="font-size: 10px; letter-spacing: 0.14em; text-transform: uppercase; text-align: right; color: {gold};">{tier}</span>
  </div>
'''
inner += '''  <div style="margin-top: auto; padding-top: 20px;"><span class="body" style="font-size: 14px;"><span style="color:#1B221F; font-weight:500;">Advisory</span> is not a lesser fact — it is a different permission. Guidance may inform a suggestion; it may never enter a ranked comparison against surveyed data.</span></div>
'''
write("Sources.dc.html", "Our sources", "04", inner)
print("03, 04 written")

exec(open("_gen.py").read().split("# ---------------------------------------------------------------- 01 title")[0])

# ---------------------------------------------------------------- 05 credibility
chain = [
 ("Publisher", "CACP / DES", "Who authored it. This is the citation."),
 ("Access route", "api.data.gov.in", "Where we fetched it. Never the citation."),
 ("Retrieved", "2026-08-28", "When we took this copy."),
 ("Content hash", "8a20bc38…", "Proves a later copy is the same document."),
 ("Licence", "UNKNOWN", "Unconfirmed. Blocks the figure from being trusted."),
]
inner = '''  <div style="padding: 34px 0 28px; display: flex; justify-content: space-between; align-items: flex-end;">
    <div class="serif" style="font-size: 46px;">What makes a figure credible</div>
    <div class="body" style="font-size: 14px; max-width: 400px; text-align: right;">Five facts travel with every value. A value missing any of them cannot enter the reasoning layer.</div>
  </div>
  <div style="display: flex; gap: 0; border: 1px solid rgba(221,227,223,0.7); background: #FFFFFF;">
'''
for i, (k, v, d) in enumerate(chain):
    bl = "" if i == 0 else "border-left: 1px solid rgba(221,227,223,0.7);"
    val_color = "#C7A03D" if k == "Licence" else "#1A3826"
    inner += f'''    <div style="flex-grow: 1; flex-basis: 0; display: flex; flex-direction: column; gap: 10px; padding: 26px 22px; {bl}">
      <span class="eyebrow">{k}</span>
      <span class="mono" style="font-size: 15px; color: {val_color}; font-weight: 500;">{v}</span>
      <span class="body" style="font-size: 13px;">{d}</span>
    </div>
'''
inner += '''  </div>
  <div style="display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 44px; padding-top: 34px; flex-grow: 1;">
    <div style="display: flex; flex-direction: column; gap: 13px;">
      <span class="serif" style="font-size: 27px;">Publisher is not the portal</span>
      <span class="body">A cost figure is authored by the Commission for Agricultural Costs and Prices. We happen to fetch it through a data portal. Citing the portal would overstate its authority and lose the real source — so the two are recorded separately and only the publisher is ever quoted.</span>
    </div>
    <div style="display: flex; flex-direction: column; gap: 13px;">
      <span class="serif" style="font-size: 27px;">A person confirms, not a script</span>
      <span class="body">A fetch cannot assert that a table was read correctly. So no figure has its confidence raised until a named person has checked the transcription and recorded the licence. Trust is never granted by automation.</span>
    </div>
  </div>
'''
write("Credibility.dc.html", "How credibility is established", "05", inner)

# ---------------------------------------------------------------- 06 caps
inner = '''  <div style="padding: 34px 0 26px; display: flex; justify-content: space-between; align-items: flex-end;">
    <div class="serif" style="font-size: 46px;">An unverified number cannot advise a farmer</div>
    <div class="body" style="font-size: 14px; max-width: 360px; text-align: right;">Not by policy. By construction — the ceiling sits below the floor required to act.</div>
  </div>
  <div style="display: flex; gap: 46px; flex-grow: 1; align-items: stretch;">
    <div style="flex-basis: 46%; display: flex; flex-direction: column; justify-content: center; gap: 22px; padding: 32px; border: 1px solid rgba(221,227,223,0.7); background: #FFFFFF;">
      <div style="display: flex; align-items: baseline; gap: 14px;">
        <span class="serif" style="font-size: 62px;">0.42</span>
        <span class="body" style="font-size: 15px;">ceiling on an unsourced<br>crop-protection finding</span>
      </div>
      <hr class="rule">
      <div style="display: flex; align-items: baseline; gap: 14px;">
        <span class="serif" style="font-size: 62px; color: #C7A03D;">0.45</span>
        <span class="body" style="font-size: 15px;">floor required before anything<br>may drive a recommendation</span>
      </div>
      <div style="padding-top: 8px;"><span style="font-size: 15px; color: #1B221F; line-height: 1.6;">The gap is deliberate. An unsourced diagnosis is <span style="font-style: italic;">structurally incapable</span> of reaching a farmer, however confident the model feels.</span></div>
    </div>
    <div style="flex-grow: 1; display: flex; flex-direction: column; gap: 20px; justify-content: center;">
      <span class="serif" style="font-size: 27px;">Every unsourced figure carries a ceiling</span>
      <span class="body">Rather than labelling uncertain data and hoping a reader notices, each unverified input is capped at the point of use. The cap propagates into everything computed from it, so an unsourced cost quietly limits the confidence of the whole crop plan — visibly, and without anyone having to remember.</span>
      <div style="display: flex; flex-direction: column; gap: 0; border-top: 1px solid rgba(221,227,223,0.7);">
'''
for label, cap, what in [("Crop-protection guidance", "0.42", "below the action floor"), ("Cost of cultivation", "0.62", "caps the whole crop plan"), ("Scheme eligibility rules", "0.55", "rules not yet verified")]:
    inner += f'''        <div style="display: flex; justify-content: space-between; align-items: baseline; padding: 14px 0; border-bottom: 1px solid rgba(221,227,223,0.7);">
          <span style="font-size: 15px; color: #1B221F;">{label}</span>
          <span style="display: flex; align-items: baseline; gap: 14px;"><span class="body" style="font-size: 13px;">{what}</span><span class="serif" style="font-size: 24px;">{cap}</span></span>
        </div>
'''
inner += '''      </div>
      <span class="body" style="font-size: 14px;">A cap lifts only when a person has confirmed the source. Nine of our ten sources are still capped today — and we would rather say so than quietly rely on them.</span>
    </div>
  </div>
'''
write("Caps.dc.html", "Why you can rely on it", "06", inner)
print("05, 06 written")

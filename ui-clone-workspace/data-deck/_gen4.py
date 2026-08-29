exec(open("_gen.py").read().split("# ---------------------------------------------------------------- 01 title")[0])

# ---------------------------------------------------------------- 07 orchestrator
mech = [
 ("Names are mapped, never guessed",
  "One table maps every source's vocabulary into ours. An unrecognised name stops the run.",
  "Fuzzy matching would fold <span class='mono' style='font-size:12px;'>Paddy (Grade A)</span> into <span class='mono' style='font-size:12px;'>Paddy (Common)</span> — two different prices, one silent error."),
 ("Disagreement is shown, not settled",
  "When two sources conflict beyond tolerance, both claims are kept and confidence drops.",
  "The system never quietly picks a winner and presents it as the answer."),
 ("Unsourced crops leave the comparison",
  "A margin ranking admits a crop only when every cost behind it is sourced.",
  "Margin is a difference of two numbers — an invented cost can win on the strength of the invention."),
 ("Guidance cannot outrank a survey",
  "Advisory material informs suggestions. It never competes in a ranked result.",
  "A confident single-district study must not outrank a 900-farmer state survey."),
]
inner = '''  <div style="padding: 34px 0 26px; display: flex; justify-content: space-between; align-items: flex-end;">
    <div class="serif" style="font-size: 46px;">Turning cluttered data into a decision</div>
    <div class="body" style="font-size: 14px; max-width: 400px; text-align: right;">Four rules stand between raw public data and anything the orchestrator is allowed to say.</div>
  </div>
  <div style="display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 22px; flex-grow: 1;">
'''
for i, (t, d, w) in enumerate(mech):
    inner += f'''    <div style="display: flex; flex-direction: column; gap: 11px; padding: 26px 26px 24px; border: 1px solid rgba(221,227,223,0.7); background: #FFFFFF;">
      <span class="eyebrow mono">Rule 0{i+1}</span>
      <span class="serif" style="font-size: 25px;">{t}</span>
      <span style="font-size: 15px; color: #1B221F; line-height: 1.55;">{d}</span>
      <span class="body" style="font-size: 13px; padding-top: 11px; border-top: 1px solid rgba(221,227,223,0.7);">{w}</span>
    </div>
'''
inner += '''  </div>
  <div style="margin-top: 24px; padding: 20px 24px; border-left: 2px solid #C7A03D; background: #FFFFFF;">
    <span style="font-size: 15px; color: #1B221F;">What reaches the FPO is not "the data we found". It is what survived four rules designed to catch the <span style="font-style: italic;">plausible wrong answer</span> — the kind that never announces itself.</span>
  </div>
'''
write("Orchestrator.dc.html", "Streamlining for the orchestrator", "07", inner)

# ---------------------------------------------------------------- 08 refusals
inner = '''  <div style="padding: 34px 0 28px;">
    <div class="serif" style="font-size: 46px; max-width: 900px;">What we refuse to do is part of the product</div>
  </div>
  <div style="display: flex; gap: 46px; flex-grow: 1;">
    <div style="flex-basis: 52%; display: flex; flex-direction: column; gap: 20px; padding: 30px; border: 1px solid rgba(221,227,223,0.7); background: #FFFFFF;">
      <span class="eyebrow">The case in one example</span>
      <span class="serif" style="font-size: 29px; line-height: 1.24;">We found a government API holding farmer records. We did not take it.</span>
      <span class="body">A state agriculture portal exposes an interface serving beneficiary registrations, farmer lists and payment records. It was reachable. We recorded it in writing as out of bounds, with the reasoning, so that nobody later finds it and assumes it was simply missed.</span>
      <hr class="rule">
      <span class="body" style="font-size: 14px;">A farmer's data belongs to the farmer. That holds whether or not a door happens to be open.</span>
    </div>
    <div style="flex-grow: 1; display: flex; flex-direction: column; gap: 0;">
'''
for t, d in [
  ("Never bypass a protection", "A blocked page and a 403 are answers, not obstacles. Where a sanctioned interface exists, we use that instead."),
  ("Never invent an agricultural figure", "A yield or subsidy rule we cannot cite is marked invented and shown as such, or the feature is dropped. There is no third option."),
  ("Never present guidance as a guarantee", "An announced support price is not a price a farmer can reach unless a centre is open. We show the distinction rather than flattening it."),
  ("Never delete good history", "A source that goes down keeps its last good copy. Nothing valid is discarded because a portal had a bad afternoon."),
]:
    inner += f'''      <div style="display: flex; flex-direction: column; gap: 6px; padding: 19px 0; border-bottom: 1px solid rgba(221,227,223,0.7);">
        <span style="font-size: 17px; color: #1A3826; font-weight: 500;">{t}</span>
        <span class="body" style="font-size: 14px;">{d}</span>
      </div>
'''
inner += '''    </div>
  </div>
  <div style="padding-top: 24px; margin-top: 20px; border-top: 1px solid rgba(221,227,223,0.7); display: flex; justify-content: space-between; align-items: baseline;">
    <span class="serif" style="font-size: 25px;">An FPO can check every number we show it.</span>
    <span class="body" style="font-size: 14px;">Source, publisher, retrieval date, and whether a person has verified it.</span>
  </div>
'''
write("Refusals.dc.html", "Why an FPO can rely on us", "08", inner)
print("07, 08 written")

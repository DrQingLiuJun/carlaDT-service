"""Semantic SVG tracing of the supplied HAUT overhead image (2048×719).

Image coordinates are registered to CARLA metres from the long straight lane
centres: north y=-13.119/-8.901 and south y=7.6/11.8. They are not inferred
from the incomplete OpenDRIVE crosswalk polygons. This is a map-specific visual
asset; other maps retain their native geometry. Source photo stays unmodified.
"""
from pathlib import Path
parts=['''<svg xmlns="http://www.w3.org/2000/svg" width="4096" height="1438" viewBox="0 0 2048 719">
<title>HAUT visual road map</title><desc>Continuous road surface, visual parking bays and crossings traced from CARLA overhead view.</desc>
<defs><pattern id="paving" width="16" height="16" patternUnits="userSpaceOnUse"><path d="M16 0H0V16" fill="none" stroke="#3c4c55" stroke-width=".7"/></pattern>
<pattern id="zebraV" width="8" height="8" patternUnits="userSpaceOnUse"><rect width="4" height="8" fill="#c4d0d6"/></pattern>
<pattern id="zebraH" width="8" height="8" patternUnits="userSpaceOnUse"><rect width="8" height="4" fill="#c4d0d6"/></pattern>
<g id="arrow"><path d="M-21 0H17M6-8L20 0 6 8" fill="none" stroke="#b4c3cc" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"/></g>
<g id="turn"><path d="M-22 0H7Q16 0 16-9V-18M9-11L16-20 23-11" fill="none" stroke="#b4c3cc" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"/></g>
<g id="straight-left"><use href="#arrow"/><path d="M-3 0L9 -12M0 -12H9V-3" fill="none" stroke="#b4c3cc" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"/></g>
<g id="straight-right"><use href="#arrow"/><path d="M-3 0L9 12M0 12H9V3" fill="none" stroke="#b4c3cc" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"/></g>
<g id="left-right"><path d="M-21 0H-2L13 -13M4 -13H13V-4M-2 0L13 13M4 13H13V4" fill="none" stroke="#b4c3cc" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"/></g>
</defs>
<rect x="15" y="10" width="2016" height="696" rx="15" fill="#1b302d" stroke="#516360" stroke-width="2"/>
<!-- One connected asphalt silhouette, with planted islands cut out. -->
<path d="M225 106C160 80 108 124 99 187C88 251 136 302 210 308L293 311V402L194 452V578L1846 578Q1948 581 1948 482V138H897V87H490V139H330Z" fill="#394955" stroke="#7b8b91" stroke-width="2.5" stroke-linejoin="round"/>
<path d="M100 265V525Q100 627 207 638H1878Q1984 636 1984 533V170Q1982 64 1878 63H216Q76 63 73 188V527" fill="none" stroke="#55635f" stroke-width="52"/>
<path d="M100 265V525Q100 627 207 638H1878Q1984 636 1984 533V170Q1982 64 1878 63H216Q76 63 73 188V527" fill="none" stroke="#34444c" stroke-width="47"/>
<path d="M100 265V525Q100 627 207 638H1878Q1984 636 1984 533V170Q1982 64 1878 63H216Q76 63 73 188V527" fill="none" stroke="url(#paving)" stroke-width="47"/>
<!-- Islands are traced from visible kerbs, not per-lane mesh patches. -->
<path d="M183 180Q190 173 212 179L280 203Q304 215 294 234Q289 246 263 240L189 219Q166 211 183 180Z" fill="#243c35" stroke="#8b9b92" stroke-width="2"/>
<rect x="430" y="276" width="105" height="167" rx="29" fill="#243c35" stroke="#7b9087" stroke-width="2"/>
<rect x="606" y="276" width="131" height="167" rx="29" fill="#243c35" stroke="#7b9087" stroke-width="2"/>
<path d="M843 273H1404Q1439 273 1440 307V410Q1440 439 1408 439H844Q812 439 812 406V303Q812 273 843 273Z" fill="#243c35" stroke="#7b9087" stroke-width="2"/>
<rect x="1580" y="275" width="176" height="24" rx="12" fill="#243c35" stroke="#7b9087" stroke-width="2"/>
<rect x="1580" y="414" width="176" height="26" rx="13" fill="#243c35" stroke="#7b9087" stroke-width="2"/>
<path d="M104 382L193 411V578L289 550V428L260 402Q183 375 104 382Z" fill="#243c35"/>
<!-- Continuous pedestrian paths and central median walkway. -->
<path d="M102 325Q150 348 199 348H430M102 385Q150 361 199 361H430M535 351H606M737 352H1439" fill="none" stroke="#82918f" stroke-width="44"/>
<path d="M102 325Q150 348 199 348H430M102 385Q150 361 199 361H430M535 351H606M737 352H1439" fill="none" stroke="#43545b" stroke-width="40"/>
<path d="M102 325Q150 348 199 348H430M102 385Q150 361 199 361H430M535 351H606M737 352H1439" fill="none" stroke="url(#paving)" stroke-width="40"/>
''']
def add(s):parts.append(s)
def rect(x,y,w,h,fill,**attrs):
    more=' '.join(f'{k.replace("_","-")}="{v}"' for k,v in attrs.items())
    add(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" fill="{fill}" {more}/>')
# White edge and centre markings visible in the image.
for y in [202,510]:
    for x1,x2 in [(889,1376)]:
        add(f'<path d="M{x1} {y}H{x2}" fill="none" stroke="#a2b3bd" stroke-width="1.5"/>')
add('<path d="M1512 301V413" fill="none" stroke="#9eafb9" stroke-width="1.5" stroke-dasharray="22 20"/>')
add('<path d="M1420 202H1764Q1824 202 1824 262V450Q1824 510 1764 510H1420" fill="none" stroke="#9eafb9" stroke-width="1.5" stroke-dasharray="22 20"/>')
add('<path d="M867 142V205H1376M867 444V510H1376" fill="none" stroke="#adbdc4" stroke-width="1.7"/>')
# Crossings are traced against actual kerbs; no floating OpenDRIVE polygons.
for x in [482,668,845,1394]:
    for y,h in [(141,131),(446,129)]:rect(x,y,19,h,'url(#zebraH)')
for x,y,w,h in [(303,307,126,20),(303,378,126,20),(540,308,60,19),(540,378,60,19)]:rect(x,y,w,h,'url(#zebraV)')
# Parking bays: shared perimeter and dividers, exactly on the visual asphalt.
add('<g fill="none" stroke="#c0ccd2" stroke-width="2">')
add('<path d="M491 88V138H885V88M1888 141H1944V568H1888ZM1611 302H1719V350H1611ZM1611 358H1719V408H1611Z"/>')
for x in [568,645,722,800]:add(f'<path d="M{x} 88V138"/>')
for y in [247,355,461]:add(f'<path d="M1888 {y}H1944"/>')
add('<path d="M196 455L289 407V551L196 605ZM196 505L289 454M196 554L289 503M867 277H944V334H867Z"/></g>')
# Explicit surveyed markings: no repeated arrows through unmarked intersections.
# West of the eastern crossing: upper W/E, lower W/E. East of it: both
# upper lanes westbound, both lower lanes eastbound (visible in the photo).
markings=[
    ('straight-left',939,170,180),('arrow',1120,170,180),('arrow',1305,170,180),
    ('arrow',939,235,0),('arrow',1120,235,0),('straight-right',1305,235,0),
    ('straight-right',939,477,180),('arrow',1120,477,180),('arrow',1305,477,180),
    ('arrow',939,541,0),('arrow',1120,541,0),('arrow',1305,541,0),
    ('straight-left',1500,170,180),('arrow',1688,170,180),
    ('straight-left',1500,235,180),('arrow',1688,235,180),
    ('arrow',1500,477,0),('straight-left',1688,477,0),
    ('arrow',1500,541,0),('straight-left',1688,541,0),
]
for kind,x,y,angle in markings:
    add(f'<use href="#{kind}" data-marking="{x}-{y}" transform="translate({x} {y}) rotate({angle})"/>')
# The narrow middle link has two northbound fork arrows. The next western
# connector has a southbound fork above the walkway and northbound below it.
for x,y,angle in [(569,303,90),(569,410,-90),(774,303,-90),(774,398,-90)]:
    add(f'<use href="#left-right" data-marking="{x}-{y}" transform="translate({x} {y}) rotate({angle}) scale(.72)"/>')
# Two marked lanes on each side of the eastern parking islands.
for x in [1478,1541]:
    add(f'<use href="#arrow" data-marking="{x}-329" transform="translate({x} 329) rotate(90) scale(.7)"/>')
    add(f'<use href="#left-right" data-marking="{x}-386" transform="translate({x} 386) rotate(-90) scale(.7)"/>')
for x in [1789,1853]:
    add(f'<use href="#straight-left" data-marking="{x}-329" transform="translate({x} 329) rotate(-90) scale(.7)"/>')
    add(f'<use href="#arrow" data-marking="{x}-386" transform="translate({x} 386) rotate(-90) scale(.7)"/>')
add('<path d="M188 143Q138 142 138 205M138 239Q163 268 203 274" fill="none" stroke="#a6b7be" stroke-width="3" stroke-dasharray="24 26"/>')
for x,y,angle in [(288,163,201),(234,274,12)]:add(f'<use href="#arrow" transform="translate({x} {y}) rotate({angle}) scale(.8)"/>')
# Buildings simplified to quiet, sharp footprints; no photographic shadows.
for x,y,w,h in [(136,413,92,42),(80,455,49,40),(125,530,39,70),(450,291,68,26),(626,291,87,27),(452,401,59,25),(631,405,73,26),(1120,275,316,144),(273,12,191,76),(1560,12,184,79),(196,614,161,83),(943,613,192,85),(1692,614,160,83)]:
    rect(x+3,y+4,w,h,'#13232b',rx=3)
    rect(x,y,w,h,'#52626b',rx=3,stroke='#7a8b92',stroke_width=1.2)
    add(f'<path d="M{x+6} {y+h/2}H{x+w-6}" stroke="#75858b" stroke-width="1"/>')
for row,xs in [(99,[936,1036,1140,1240,1340,1810,1866]),(291,[989,1091]),(407,[890]),(598,[440,569,676,819,1284,1390,1484,1591])]:
    for x in xs:rect(x,row,36,24,'#5b6c71',rx=2,stroke='#88988f',stroke_width=1)
# Small canopy symbols help orient without photographic clutter.
for x,y,r in [(x,118,8) for x in range(920,1830,58)]+[(x,595,7) for x in range(396,1650,54)]+[(x,425,7) for x in range(950,1115,40)]+[(1596,286,7),(1735,286,7),(1596,427,7),(1735,427,7)]:
    add(f'<circle cx="{x}" cy="{y}" r="{r}" fill="#35564a" stroke="#52745d" stroke-width="1"/>')
add('</svg>')
Path('frontend/public/maps/haut-visual.svg').write_text('\n'.join(parts))

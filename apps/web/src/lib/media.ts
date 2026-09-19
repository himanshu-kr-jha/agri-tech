/**
 * Where the landing page's footage lives.
 *
 * The split is deliberate. Posters are committed to `public/hero/` and the videos are not:
 * five clips is several megabytes that would sit in every clone forever, while the posters
 * are ~660 KB and buy something the videos cannot — a hero that renders correctly with no
 * network at all. `make seed && make dev` on a laptop with the wifi off still reproduces
 * the demo, which `docs/MVP-SCOPE.md` requires of it.
 *
 * So `NEXT_PUBLIC_VIDEO_BASE_URL` being unset is a supported mode, not a misconfiguration.
 * `videoSrc()` returns null and the carousel runs as a poster slideshow.
 */

const BASE = process.env.NEXT_PUBLIC_VIDEO_BASE_URL?.replace(/\/$/, "") || null;

/**
 * Clip id → the file's name in blob storage.
 *
 * This map exists because what is currently hosted is the **untranscoded source set**,
 * under its original camera/stock filenames, totalling ~68 MB — where
 * `scripts/build_hero_media.py` produces the same five clips at ~3.8 MB. The originals are
 * usable rather than ideal: every one has its `moov` atom at the front and the store serves
 * byte ranges, so a browser streams only the seconds it plays instead of the whole file.
 * It still costs several times what the optimised set would.
 *
 * **When the optimised renditions are uploaded, this whole map goes away** — their names
 * already match the clip ids, so `videoSrc` falls back to `${clip}.mp4` for anything absent
 * here. Deleting an entry is the migration.
 */
const CLIP_FILES: Record<string, string> = {
  "hero-01-paddy": "14416222-hd_1920_1080_60fps.mp4",
  "hero-02-grading": "17867755-hd_1920_1080_60fps.mp4",
  "hero-03-harvest": "6780097-uhd_3840_2160_25fps.mp4",
  "strip-01-advisory": "istockphoto-1365398932-640_adpp_is.mp4",
  "strip-02-officer": "istockphoto-1492945427-640_adpp_is.mp4",
};

/** The blob URL for a clip, or null when no CDN is configured. */
export function videoSrc(clip: string): string | null {
  if (!BASE || !clip) return null;
  return `${BASE}/${CLIP_FILES[clip] ?? `${clip}.mp4`}`;
}

/** The committed poster. Always available — that is the whole point of committing them. */
export function posterSrc(clip: string): string {
  return `/hero/${clip}.jpg`;
}

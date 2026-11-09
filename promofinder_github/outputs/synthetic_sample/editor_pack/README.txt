Editor pack: turn ranked promos into things a video editor can use directly.

Writes (for the top N promos, single + cold-open):
  clip_sheet.csv     one row per segment: promo, episode file, in/out (seconds + timecode), caption, notes
  briefs.md          one short brief per promo: timings, why, script excerpt with HOOK / CLIFF markers
  promos.edl         CMX3600 EDL (import into Premiere / Resolve / FCP via EDL import)
  cut_promos.sh/.bat ffmpeg commands that cut each promo from the episode videos (frame-accurate re-encode)

Assumption: each episode's video sits in VIDEO_DIR with the same name as its script file and VIDEO_EXT
(e.g. "episode-003-Episode 123.txt" -> "videos/episode-003-Episode 123.mp4"). Both are parameters.

fps used for timecodes: 30

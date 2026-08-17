from __future__ import annotations

# Events-only scope: every call site (app/calendar_service.py) only ever uses
# service.events(), never calendarList()/acl()/calendars(), so this is
# deliberately narrower than the full "calendar" scope, which would also let
# the credential delete calendars outright or change sharing/ACLs.
SCOPES = ["https://www.googleapis.com/auth/calendar.events"]

DEFAULT_TIMEZONE = "America/Los_Angeles"


# Google Calendar IDs (Settings > Integrate calendar > Calendar ID), keyed by
# display name. This is what the service account needs to address the
# calendar via the Calendar API.
CALENDAR_LINKS = {
    "SF Arts/Culture": "7f66e10ca74622780fdf0db852f0dc8e4be2272cf206bfc8cf83f2eaefc8abdf@group.calendar.google.com",
    "SF Community": "c40ce35591588f6a8cf1d14e96f4ec215f2d812857382a0fb7253eabea1a0154@group.calendar.google.com",
    "SF Fun Cheap": "60a19fdad14c75dc604082f022416e48c2d30dc440502a5e80bf410d32570d1d@group.calendar.google.com",
    "SF Partiful": "9d7c77c609ffc954909e2a0cb72e2c2b5029048fe87d0ba6a035ccac18e1472a@group.calendar.google.com",
    "SF Tech": "45264416fab34dddf5fff1ca40931d59a13f865ec441d158030be512b30d6b15@group.calendar.google.com",
    "SF Bars": "9c8685a68b697409a5bffa6ce3011651930fa18572dad9ef435215753a43de22@group.calendar.google.com",
    "SF Dancing": "704367c0fe7ec0383a79ab3bd6a4388d8c867642120862ffa11191fdb27e407f@group.calendar.google.com",
    "SF Exercise": "2a8d48b484e0b7d54bd801ad4849798902dbb347781ab1371b06f6cddaad9a9f@group.calendar.google.com",
    "SF Zen Center": "d668dd99f1b1452b81324f8024930e562097bc7abe2f54c45d4816f3b26c8511@group.calendar.google.com",
    "SF Shows": "88eb45ae7b30e306d2d467e36f616db20abf74008d161ed225419e4e2a4b9538@group.calendar.google.com",
}


# Maps display name → actual Google Calendar ID. This is what gets passed to
# the Calendar API — never a calendar name.
CALENDAR_IDS: dict[str, str] = dict(CALENDAR_LINKS)


# Per-calendar duplicate-detection rules, checked across every source feeding
# that calendar (not just within one scraper) so e.g. two different arts
# calendars covering the same gallery opening get caught. Two events are
# duplicates if they match on every field in "fields" and their start times
# are within "time_window_minutes" of each other. Matching is chained: if A
# and B are within the window and B and C are within the window, A/B/C are
# all treated as one duplicate group even if A and C alone are not.
# Calendars not listed here fall back to DEFAULT_DEDUP_RULE (exact title +
# exact start time, i.e. the original behavior).
DEFAULT_DEDUP_RULE: dict = {"fields": ("summary",), "time_window_minutes": 0}

DEDUP_RULES: dict[str, dict] = {
    # Art gallery openings get posted with different titles/wording by
    # different sources (e.g. ArtBae vs. ArtBusiness), but a real duplicate
    # is always the same gallery at the same time, so match on location only.
    "SF Arts/Culture": {"fields": ("location",), "time_window_minutes": 30},
}




SOURCES: dict[str, dict] = {
    "the_faight": {
        "label": "The Faight",
        "location": "Lower Haight",
        "location_link": "https://maps.app.goo.gl/sD1asWWUYL11KqmEA",
        "emoji": "🔮",
        "display_url": "https://www.thefaight.com/events",
        "calendar": "SF Arts/Culture",
        "enabled": True,
    },
    "decentered_featured_events": {
        "label": "Decentered Featured Events",
        "location": "SOMA 8th St",
        "location_link": "https://maps.app.goo.gl/vzyNdBP39hJtJ2XC9",
        "emoji": "😵‍💫",
        "display_url": "https://decentered.org/events",
        "calendar": "SF Arts/Culture",
        "enabled": True,
    },
    "funcheap": {
        "label": "SF Funcheap",
        "emoji": "😜",
        "display_url": "https://sf.funcheap.com/region/san-francisco/",
        "calendar": "SF Fun Cheap",
        "enabled": True,
    },
    "luma": {
        "label": "Luma",
        "emoji": "💡",
        "display_url": "https://luma.com/sf",
        "calendar": "SF Tech",
        "enabled": True,
    },
    "decentered_community_events": {
        "label": "Decentered Community Events",
        "location": "SOMA 8th St",
        "location_link": "https://maps.app.goo.gl/vzyNdBP39hJtJ2XC9",
        "emoji": "👥",
        "display_url": "https://decentered.org/events",
        "calendar": "SF Community",
        "enabled": True,
    },
    "mannys": {
        "label": "Manny's: Community, Politics, and Culture",
        "location": "Mission 16th St",
        "location_link": "https://maps.app.goo.gl/wyEqhBaKK8M7sU1Q9",
        "emoji": "👨‍🦰",
        "display_url": "https://www.eventbrite.com/o/mannys-community-politics-and-culture-15114280512",
        "calendar": "SF Community",
        "enabled": True,
    },
    "the_sf_nook": {
        "label": "The SF Nook: SF Event Space",
        "location": "Civic Center on Market St",
        "location_link": "https://maps.app.goo.gl/MbiV4DbkXNUp12QLA",
        "emoji": "🏠",
        "display_url": "https://www.thesfnook.com/events",
        "calendar": "SF Community",
        "enabled": True,
    },
    "luma_the_commons": {
        "label": "The Commons: Third Space",
        "location": "Hayes Valley",
        "location_link": "https://maps.app.goo.gl/URPfH9ePaBTm3YRd9",
        "emoji": "🏛️",
        "display_url": "https://luma.com/thecommons",
        "calendar": "SF Community",
        "enabled": True,
    },
    "luma_future_of_us": {
        "label": "Future of Us",
        "emoji": "⚡",
        "display_url": "https://luma.com/future-of-us",
        "calendar": "SF Community",
        "enabled": True,
    },
    "the_sf_contemplarium": {
        "label": "The SF Contemplarium",
        "emoji": "📓",
        "display_url": "https://luma.com/sfcontemplarium",
        "calendar": "SF Community",
        "enabled": True,
    },
    "luma_tiat": {
        "label": "TIAT Art and Tech",
        "location": "Downtown: Powell and O'Farrell",
        "location_link": "https://maps.app.goo.gl/phgTf8BvmnwwKht87",
        "emoji": "🤖",
        "display_url": "https://luma.com/tiat",
        "calendar": "SF Arts/Culture",
        "enabled": True,
    },
    "partiful": {
        "label": "Partiful",
        "emoji": "🥳",
        "display_url": "https://partiful.com/explore/sf",
        "calendar": "SF Partiful",
        "enabled": True,
    },
    "mox": {
        "label": "Mox Event Space",
        "location": "Mission 13th St",
        "location_link": "https://maps.app.goo.gl/1rUtdL99NgpzCrcbA",
        "emoji": "💻",
        "display_url": "https://moxsf.com/events",
        "calendar_link": "https://calendar.google.com/calendar/embed?src=6395b6c6ab85cf5ff3b6a1e59bc218ec592b74bfebf94821158bcf7e56c23ab1%40group.calendar.google.com&ctz=America%2FLos_Angeles",
        "calendar": "SF Tech",
        "enabled": True,
    },
    "artbae": {
        "label": "Art Bae",
        "emoji": "🎨",
        "display_url": "https://www.artbae.info/map-calendar",
        "calendar": "SF Arts/Culture",
        "enabled": True,
    },
    "artbusiness": {
        "label": "SF Art Galleries - Openings & Events",
        "emoji": "🖼️",
        "display_url": "https://calendar.google.com/calendar/embed?src=33alanb%40gmail.com&ctz=America%2FLos_Angeles",
        "calendar_link": "https://calendar.google.com/calendar/embed?src=33alanb%40gmail.com&ctz=America%2FLos_Angeles",
        "calendar": "SF Arts/Culture",
        "enabled": True,
    },
    "sf_bar_guide": {
        "label": "SF Bar Guide",
        "display_url": "https://www.sfbarguide.com/",
        "calendar": "SF Bars",
        "enabled": True,
    },
    "golden_sardine": {
        "label": "Golden Sardine",
        "location": "North Beach",
        "location_link": "https://www.google.com/maps/search/?api=1&query=362+Columbus+Ave%2C+San+Francisco%2C+CA+94133",
        "emoji": "🐟",
        "display_url": "https://www.goldensardinesf.com/events",
        "calendar": "SF Bars",
        "enabled": True,
    },
    "rootdivision": {
        "label": "Root Division",
        "location": "Mission St",
        "location_link": "https://www.google.com/maps/search/?api=1&query=1131+Mission+Street%2C+San+Francisco%2C+CA+94103",
        "emoji": "🖌️",
        "display_url": "https://rootdivision.org/gallery/events/",
        "calendar": "SF Arts/Culture",
        "enabled": True,
    },
    "madrone_art_bar": {
        "label": "Madrone Art Bar",
        "location": "Alamo Square",
        "location_link": "https://maps.app.goo.gl/drHLFmYXNrUshseR6",
        "emoji": "🎨",
        "display_url": "https://www.eventbrite.com/o/madrone-art-bar-33448786911",
        "calendar": "SF Bars",
        "enabled": True,
    },
    "sf_climate_action_club": {
        "label": "SF Climate Action Club",
        "emoji": "🌍",
        "display_url": "https://luma.com/climateactionclub",
        "calendar": "SF Community",
        "enabled": True,
    },
    "sf_craft_club": {
        "label": "SF Craft Club",
        "emoji": "🧶",
        "display_url": "https://luma.com/user/sfcraftclub",
        "calendar": "SF Arts/Culture",
        "enabled": True,
    },
    "gistirl": {
        "label": "GistIRL: Make Friends and Network",
        "emoji": "🤝",
        "display_url": "https://app.gistirl.com/",
        "calendar": "SF Community",
        "enabled": True,
    },
    "unplug_and_play_collective": {
        "label": "Unplug and Play Collective",
        "emoji": "📵",
        "display_url": "https://www.unplugandplaycollective.com/",
        "calendar": "SF Community",
        "enabled": True,
    },
    "moonlit_moves": {
        "label": "Moonlit Moves: Mission 22nd St",
        "location": "The Polish Club Inc., 3040 22nd St",
        "location_link": "https://www.google.com/maps/search/?api=1&query=The+Polish+Club+Inc.%2C+3040+22nd+St%2C+San+Francisco%2C+CA+94110",
        "emoji": "🌙",
        "display_url": "https://calendar.google.com/calendar/embed?src=f3bfcf5b10ff8cb2ba35abba749ccd68bc8347e2d522e6baca32448c9b2695cc%40group.calendar.google.com&ctz=America%2FLos_Angeles",
        "calendar_link": "https://calendar.google.com/calendar/embed?src=f3bfcf5b10ff8cb2ba35abba749ccd68bc8347e2d522e6baca32448c9b2695cc%40group.calendar.google.com&ctz=America%2FLos_Angeles",
        "calendar": "SF Dancing",
        "enabled": False,
    },
    "community_music_hangout": {
        "label": "Community Music Hangout",
        "location": "Golden Gate Park (15th St) / Noe Valley, check website",
        "emoji": "🎷",
        "description": "Sing or play instruments with community",
        "display_url": "https://calendar.google.com/calendar/embed?src=88c5018286c9ab2d0e27326287e61a2b5d42b3ed4008ba650b81f054f65026dd%40group.calendar.google.com&ctz=America%2FLos_Angeles",
        "calendar_link": "https://calendar.google.com/calendar/embed?src=88c5018286c9ab2d0e27326287e61a2b5d42b3ed4008ba650b81f054f65026dd%40group.calendar.google.com&ctz=America%2FLos_Angeles",
        "calendar": "SF Community",
        "enabled": True,
    },
    "fat_boys_run_club": {
        "label": "Fat Boys Run Club",
        "emoji": "🏃",
        "display_url": "https://www.heylo.com/g/75ea182e-9df2-4b4d-bc78-a2e299384993",
        "calendar": "SF Exercise",
        "enabled": True,
    },
    "midnight_runners": {
        "label": "Midnight Runners SF",
        "emoji": "🏃",
        "display_url": "https://www.heylo.com/g/-LmBjhGfivWBeac11cNQ",
        "calendar": "SF Exercise",
        "enabled": True,
    },
    "november_project": {
        "label": "November Project SF",
        "emoji": "🏃",
        "display_url": "https://www.heylo.com/g/48f5e552-13d3-4987-bd0b-66e8855dfd46",
        "calendar": "SF Exercise",
        "enabled": True,
    },
    "page_street_fit": {
        "label": "Page Street Fit",
        "emoji": "🏃",
        "display_url": "https://www.heylo.com/g/6e3b8574-b970-4713-995a-1c641daeca26",
        "calendar": "SF Exercise",
        "enabled": True,
    },
    "sf_pickup_volleyball": {
        "label": "SF Pickup Volleyball",
        "emoji": "🏐",
        "display_url": "https://www.heylo.com/g/-LsD1YBcDKPOcrsMQ-mT",
        "calendar": "SF Exercise",
        "enabled": True,
    },
    "sf_beach_volleyball": {
        "label": "San Francisco Beach Volleyball - SFBV",
        "location": "Ocean Beach",
        "location_link": "https://www.google.com/maps/search/?api=1&query=Ocean+Beach%2C+San+Francisco%2C+CA",
        "emoji": "🏐",
        "display_url": "https://www.heylo.com/g/7b9b7d08-d381-4280-bbc7-612795d40302",
        "calendar": "SF Exercise",
        "enabled": True,
    },
    "nob_hill_run_club": {
        "label": "Nob Hill Run Club",
        "emoji": "🏃",
        "display_url": "https://partiful.com/u/gaH33LxCrvQo0r1F2Y5M",
        "calendar": "SF Exercise",
        "enabled": True,
    },
    "gathersf": {
        "label": "GatherSF",
        "emoji": "👥",
        "display_url": "https://partiful.com/u/HoM5CgWY4UxtI5vu9HtU",
        "calendar": "SF Community",
        "enabled": True,
    },
    "studio_203_figure_drawing": {
        "label": "Studio 203: Figure Drawing",
        "location": "1890 Bryant St",
        "location_link": "https://www.google.com/maps/search/?api=1&query=1890+Bryant+St%2C+San+Francisco%2C+CA",
        "emoji": "🧍",
        "display_url": "https://www.meetup.com/studio-203-figure-drawing/",
        "calendar": "SF Arts/Culture",
        "enabled": True,
    },
    "sf_chess_club": {
        "label": "San Francisco Chess Club",
        "emoji": "♟️",
        "display_url": "https://partiful.com/u/98UJpsxnnCr8p7cb77hD",
        "calendar": "SF Community",
        "enabled": True,
    },
    "touch_grass_walk_club": {
        "label": "Touch Grass Walk Club",
        "emoji": "🚶",
        "display_url": "https://partiful.com/u/3Kd8VzusjiFIN0wx4TVs",
        "calendar": "SF Community",
        "enabled": True,
    },
    "board_games_egl": {
        "label": "Board Games with EGL",
        "emoji": "🎲",
        "display_url": "https://www.heylo.com/g/12979145-cf38-42c9-b755-e3a27b458bf9",
        "calendar": "SF Community",
        "enabled": True,
    },
    "the_web_sf": {
        "label": "The Web SF",
        "location": "Lower Haight",
        "location_link": "https://maps.app.goo.gl/sD1asWWUYL11KqmEA",
        "emoji": "🕸️",
        "display_url": "https://www.heylo.com/g/1fda3590-3f27-4ee0-afc1-a63473b8a200",
        "calendar": "SF Arts/Culture",
        "enabled": True,
    },
    "lower_haight_local": {
        "label": "Lower Haight Local",
        "location": "Lower Haight",
        "location_link": "https://maps.app.goo.gl/sD1asWWUYL11KqmEA",
        "emoji": "📰",
        "display_url": "https://www.heylo.com/g/18608def-640e-4bb9-8331-1d28f1908040",
        "calendar": "SF Community",
        "enabled": True,
    },
    "sapiens": {
        "label": "Sapiens",
        "emoji": "✷",
        "display_url": "https://www.heylo.com/g/b30541ef-38c1-40c6-af55-3d100bf5d93d",
        "calendar": "SF Community",
        "enabled": True,
    },
    "bad_art_club": {
        "label": "Bad Art Club",
        "emoji": "🎨",
        "display_url": "https://www.eventbrite.com/cc/bad-art-club-4684923",
        "calendar": "SF Community",
        "enabled": True,
    },
    "founders_running_club": {
        "label": "Founders Running Club San Francisco",
        "emoji": "🏃",
        "display_url": "https://www.heylo.com/g/1270104d-2bf6-4f8c-ae29-22ef502df080",
        "calendar": "SF Tech",
        "enabled": True,
    },
    # Meetup.com sources. All get the shared 🧑‍🤝‍🧑 prefix (marks them as
    # Meetup-sourced) followed by a per-source emoji.
    "meetup_book_club": {
        "label": "The San Francisco 'Not Quite a Book Club' Book Club",
        "emoji": "🧑‍🤝‍🧑📚",
        "display_url": "https://www.meetup.com/the-san-francisco-not-quite-a-book-club-book-club/",
        "calendar": "SF Community",
        "enabled": True,
    },
    "meetup_sf_social_mixers": {
        "label": "SF Social Mixers and Networking",
        "emoji": "🧑‍🤝‍🧑🍸",
        "display_url": "https://www.meetup.com/sf-social-mixers-and-networking/",
        "calendar": "SF Community",
        "enabled": True,
    },
    "meetup_20_30_somethings": {
        "label": "20 & 30-somethings friends & fun in SF",
        "emoji": "🧑‍🤝‍🧑🎉",
        "display_url": "https://www.meetup.com/20-somethings-friends-fun-in-sf/",
        "calendar": "SF Community",
        "enabled": True,
    },
    "meetup_sf_philosophy_reading_group": {
        "label": "San Francisco Philosophy Reading Group",
        "emoji": "🧑‍🤝‍🧑🤔",
        "display_url": "https://www.meetup.com/sf-philosophy-reading-group/",
        "calendar": "SF Community",
        "enabled": True,
    },
    "meetup_music_jam_sf": {
        "label": "Music Jam SF",
        "emoji": "🧑‍🤝‍🧑🎶",
        "display_url": "https://www.meetup.com/meetup-group-dvhbxtfg/",
        "calendar": "SF Community",
        "enabled": True,
    },
    "meetup_global_ai_makers": {
        "label": "Global AI Makers • West Coast",
        "emoji": "🧑‍🤝‍🧑🧠",
        "display_url": "https://www.meetup.com/global-ai-makers-san-francisco/",
        "calendar": "SF Tech",
        "enabled": True,
    },
    "meetup_sf_startup_pitch_networking": {
        "label": "San Francisco Startup Pitch and Networking",
        "emoji": "🧑‍🤝‍🧑🚀",
        "display_url": "https://www.meetup.com/sanfrancisco-startup-pitch-and-networking/",
        "calendar": "SF Tech",
        "enabled": True,
    },
    "meetup_baysocials": {
        "label": "Bay Area Socials",
        "emoji": "🧑‍🤝‍🧑🌉",
        "display_url": "https://www.meetup.com/baysocials/",
        "calendar": "SF Community",
        "enabled": True,
    },
    "meetup_sf_game_group": {
        "label": "Play Games Learn Names",
        "emoji": "🧑‍🤝‍🧑🃏",
        "display_url": "https://www.meetup.com/san-francisco-game-meetup-group/",
        "calendar": "SF Community",
        "enabled": True,
    },
    "meetup_sf_movie_club": {
        "label": "San Francisco Movie Club",
        "emoji": "🧑‍🤝‍🧑🎬",
        "display_url": "https://www.meetup.com/sf-movie-club/",
        "calendar": "SF Community",
        "enabled": True,
    },
    "meetup_sf_code_coffee": {
        "label": "San Francisco AI Code and Coffee",
        "emoji": "🧑‍🤝‍🧑☕",
        "display_url": "https://www.meetup.com/sf-code-coffee/",
        "calendar": "SF Tech",
        "enabled": True,
    },
    "meetup_sf_vegan_society": {
        "label": "San Francisco Vegan Society Events",
        "emoji": "🧑‍🤝‍🧑🥦",
        "display_url": "https://www.meetup.com/sfvegansociety/",
        "calendar": "SF Community",
        "enabled": True,
    },
    "meetup_mission_fun_runs": {
        "label": "SF Mission Fun Runs",
        "emoji": "🧑‍🤝‍🧑👟",
        "display_url": "https://www.meetup.com/missionfunruns/",
        "calendar": "SF Community",
        "enabled": True,
    },
    "meetup_blood_on_the_clocktower": {
        "label": "San Francisco Bay Area Blood on the Clocktower",
        "emoji": "🧑‍🤝‍🧑🕰️",
        "display_url": "https://www.meetup.com/san-francisco-blood-on-the-clocktower/",
        "calendar": "SF Community",
        "enabled": True,
    },
    "meetup_sf_artsy_stuff": {
        "label": "San Francisco Artsy Stuff",
        "emoji": "🧑‍🤝‍🧑🖌️",
        "display_url": "https://www.meetup.com/meetup-group-glpdmivm/",
        "calendar": "SF Arts/Culture",
        "enabled": True,
    },
    "meetup_free_yoga_sf": {
        "label": "Free Yoga SF",
        "emoji": "🧑‍🤝‍🧑🧘",
        "display_url": "https://www.meetup.com/fitnesssf/",
        "calendar": "SF Exercise",
        "enabled": True,
    },
    "meetup_bay_area_social_scene": {
        "label": "Bay Area Social Scene",
        "emoji": "🧑‍🤝‍🧑🎡",
        "display_url": "https://www.meetup.com/bay-area-social-scene/",
        "calendar": "SF Community",
        "enabled": True,
    },
    "meetup_sf_photographers": {
        "label": "San Francisco Photographers",
        "emoji": "🧑‍🤝‍🧑📷",
        "display_url": "https://www.meetup.com/sf-photo/",
        "calendar": "SF Community",
        "enabled": True,
    },
    "meetup_sf_sketchers": {
        "label": "SF Sketchers",
        "emoji": "🧑‍🤝‍🧑✏️",
        "display_url": "https://www.meetup.com/sf-sketchers/",
        "calendar": "SF Arts/Culture",
        "enabled": True,
    },
    "sf_zen_center": {
        "label": "SF Zen Center",
        "location": "Hayes Valley",
        "location_link": "https://www.google.com/maps/search/?api=1&query=300+Page+Street%2C+San+Francisco%2C+CA+94102",
        "emoji": "☯️",
        "display_url": "https://www.sfzc.org/city-center-calendar",
        "calendar": "SF Zen Center",
        "enabled": True,
    },
    "fort_mason_center": {
        "label": "Fort Mason Center for Arts & Culture",
        "location": "Marina District",
        "location_link": "https://www.google.com/maps/search/?api=1&query=2+Marina+Blvd%2C+San+Francisco%2C+CA+94123",
        "emoji": "⛵",
        "display_url": "https://www.eventbrite.com/o/20246696685",
        "calendar": "SF Arts/Culture",
        "enabled": True,
    },
    "a_listers_entertainment": {
        "label": "A Listers Entertainment",
        "emoji": "🌃",
        "display_url": "https://www.eventbrite.com/o/12913251409",
        "calendar": "SF Bars",
        "enabled": True,
    },
    "fog_city_run": {
        "label": "Fog City Run",
        "location": "Marina District: The Blue Light, 1979 Union St",
        "location_link": "https://www.google.com/maps/search/?api=1&query=1979+Union+St%2C+San+Francisco%2C+CA+94123",
        "emoji": "🏃",
        "display_url": "https://www.heylo.com/g/eba0b87a-f4ca-4ff2-bdfb-0d6b4729eb84",
        "calendar": "SF Exercise",
        "enabled": True,
    },
    "presidio": {
        "label": "Presidio Events",
        "emoji": "🌲",
        "display_url": "https://presidio.gov/explore/events",
        "calendar": "SF Community",
        "enabled": True,
    },
    "dance_fridays": {
        "label": "Dance Fridays",
        "emoji": "💃",
        "display_url": "https://www.eventbrite.com/o/dance-fridays-8106527232",
        "calendar": "SF Dancing",
        "enabled": True,
    },
    "sfmoma": {
        "label": "SFMOMA",
        "location": "SoMA",
        "location_link": "https://www.google.com/maps/search/?api=1&query=151+Third+Street%2C+San+Francisco%2C+CA+94103",
        "emoji": "🏛️",
        "display_url": "https://www.sfmoma.org/events/",
        "calendar": "SF Arts/Culture",
        "enabled": True,
    },
    "bats_improv": {
        "label": "BATS Improv",
        "emoji": "🎭",
        "display_url": "https://www.eventbrite.com/o/bats-improv-shows-120768857464",
        "calendar": "SF Shows",
        # Appended as the last line of the event description, before the
        # standard site footer. Requested by the user for this source.
        "promo_text": "Looking for shows? Please check",
        "promo_url": "https://bayareashows.org/",
        "enabled": True,
    },
}

# Maps Google Calendar display name → list of scraper module names (under scrapers/).
# Use CALENDAR_IDS[name] to get the actual calendar ID to push events to.
CALENDARS: dict[str, list[str]] = {
    cal: [src for src, meta in SOURCES.items() if meta["calendar"] == cal and meta.get("enabled", True)]
    for cal in dict.fromkeys(meta["calendar"] for meta in SOURCES.values() if meta.get("enabled", True))
}


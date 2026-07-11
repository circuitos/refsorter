"""Model-facing schema: the system prompt, the record_artwork tool, and the
canonical movement list with its display info.

MOVEMENT_CANON and MOVEMENT_INFO must stay in sync: every canon value needs an
INFO entry (years, blurb, wiki slug); "Other" alone has null years and wiki.
"""

MOVEMENT_CANON = [
    "Medieval & Gothic", "Renaissance", "Mannerism", "Baroque", "Ukiyo-e",
    "Rococo", "Neoclassicism", "Romanticism", "Academic art", "Realism",
    "Impressionism", "Post-Impressionism", "Symbolism", "Tonalism",
    "Art Nouveau", "Expressionism", "Shin-hanga", "Fauvism", "Cubism",
    "Futurism", "Abstract art", "Surrealism", "Socialist Realism",
    "Naive art", "Contemporary", "Other",
]

MOVEMENT_INFO = {
    "Medieval & Gothic": {"years": [500, 1400], "wiki": "Gothic_art",
        "blurb": "Sacred art of manuscript, panel and fresco: flattened space, gold grounds, hierarchical scale. The image serves doctrine before observation; naturalism creeps in late through Giotto and the International Gothic courts."},
    "Renaissance": {"years": [1400, 1530], "wiki": "Renaissance_art",
        "blurb": "Perspective, anatomy and classical order rediscovered. From Masaccio's weight to Leonardo's sfumato and Titian's colour, painting becomes a discipline of seeing built on drawing, proportion and humanist subjects."},
    "Mannerism": {"years": [1520, 1600], "wiki": "Mannerism",
        "blurb": "The generation after Raphael stretches the rules: elongated figures, acid colour, crowded unstable compositions, virtuosity for its own sake. Elegance and artifice over balance. Pontormo, Bronzino, El Greco."},
    "Baroque": {"years": [1600, 1730], "wiki": "Baroque_painting",
        "blurb": "Drama as doctrine: raking light, deep shadow, diagonal movement, theatrical immediacy. Caravaggio's tenebrism, Rubens's flesh, Rembrandt's introspection. Painting built to overwhelm and persuade."},
    "Ukiyo-e": {"years": [1620, 1900], "wiki": "Ukiyo-e",
        "blurb": "Pictures of the floating world: Edo woodblock prints of actors, courtesans, landscapes and legends. Flat colour inside a decisive keyline, radical cropping, graded bokashi skies. Hokusai's waves and Hiroshige's stations reshaped Western art the moment they reached Paris."},
    "Rococo": {"years": [1720, 1780], "wiki": "Rococo",
        "blurb": "Baroque gone lightweight and private: pastel palettes, curling forms, fetes galantes and boudoir mythology. Watteau, Boucher, Fragonard. Decoration, flirtation, and brushwork of feathery speed."},
    "Neoclassicism": {"years": [1760, 1830], "wiki": "Neoclassicism",
        "blurb": "Reaction against Rococo frivolity: severe contours, frozen gesture, moral subjects from antiquity. David's oaths and deaths, Ingres's line. Drawing rules colour, virtue rules pleasure."},
    "Romanticism": {"years": [1780, 1850], "wiki": "Romanticism",
        "blurb": "Feeling over reason: storms, ruins, revolutions and the sublime. Gericault and Delacroix loosen the brush; Friedrich turns landscape into metaphysics; Aivazovsky makes the sea a protagonist."},
    "Academic art": {"years": [1820, 1900], "wiki": "Academic_art",
        "blurb": "The salon standard: polished finish, historical and mythological machinery, figure drawing perfected through the academies. Later a foil for every avant-garde, but the training ground of most of them."},
    "Realism": {"years": [1840, 1920], "wiki": "Realism_(art_movement)",
        "blurb": "Paint what is actually there: labour, mud, provincial life, unidealized faces. Courbet in France; in Russia the Peredvizhniki turn it into a national school of landscape and social observation."},
    "Impressionism": {"years": [1860, 1920], "wiki": "Impressionism",
        "blurb": "Optical immediacy: broken colour, visible strokes, modern life and weather painted on the spot. Light is the true subject and form dissolves into its effects. Extends late through Russian and Soviet plein-air schools."},
    "Post-Impressionism": {"years": [1885, 1910], "wiki": "Post-Impressionism",
        "blurb": "Impressionism's palette turned toward structure and symbol: Cezanne's geometry, Van Gogh's loaded stroke, Gauguin's flat arcadias, Seurat's dots. The bridge to everything modern."},
    "Symbolism": {"years": [1880, 1910], "wiki": "Symbolism_(arts)",
        "blurb": "Inner states over outer facts: myth, dream, death and eros rendered through suggestion. Moreau, Redon, Vrubel. Colour and distortion as psychology rather than description."},
    "Tonalism": {"years": [1880, 1915], "wiki": "Tonalism",
        "blurb": "Landscape filtered through mist and memory: narrow value ranges, muted palettes, twilight moods. Whistler's nocturnes and Inness's late work. Atmosphere as the whole subject."},
    "Art Nouveau": {"years": [1890, 1910], "wiki": "Art_Nouveau",
        "blurb": "Design invades painting: whiplash line, flattened ornament, botanical arabesque. Klimt and Mucha fuse figure, pattern and gold into decorative total works."},
    "Expressionism": {"years": [1905, 1935], "wiki": "Expressionism",
        "blurb": "Colour and distortion as raw feeling: Die Brucke's jagged cities, Kandinsky's road toward abstraction, Schiele's nerves. The world painted as it presses on the psyche."},
    "Shin-hanga": {"years": [1915, 1962], "wiki": "Shin-hanga",
        "blurb": "The 'new prints' revival: publisher-led woodblock art fusing ukiyo-e craft with Western light and perspective. Hasui's twilit streets and Yoshida's mountain series build painterly atmosphere from dozens of hand-printed colour blocks - travel, weather and nostalgia as the ruling subjects."},
    "Fauvism": {"years": [1904, 1910], "wiki": "Fauvism",
        "blurb": "The wild beasts: colour unchained from description. Matisse and Derain paint red trees and green faces. A short blaze that permanently freed the palette."},
    "Cubism": {"years": [1907, 1920], "wiki": "Cubism",
        "blurb": "Form dismantled and reassembled from multiple viewpoints; space flattened into faceted planes. Picasso and Braque, analytic then synthetic. The grammar of most later abstraction."},
    "Futurism": {"years": [1909, 1930], "wiki": "Futurism",
        "blurb": "Speed, machines and the modern city worshipped in fractured, dynamic planes. Boccioni and Balla paint motion itself. Energy over object."},
    "Abstract art": {"years": [1910, 2026], "wiki": "Abstract_art",
        "blurb": "Painting released from depiction: pure colour, form and gesture, from Kandinsky and Malevich through mid-century gesture and colour-field to the present."},
    "Surrealism": {"years": [1920, 1950], "wiki": "Surrealism",
        "blurb": "The unconscious as subject: dream logic, uncanny juxtaposition, automatic technique. Dali's precision, Ernst's collage, Magritte's deadpan riddles."},
    "Socialist Realism": {"years": [1930, 1991], "wiki": "Socialist_realism",
        "blurb": "The Soviet official style: optimistic, legible, heroic labour and public life in academic technique. Beside the doctrine, a vast plein-air school of genuine landscape painting worked under its umbrella."},
    "Naive art": {"years": [1880, 2026], "wiki": "Na\u00efve_art",
        "blurb": "Self-taught vision: flattened perspective, meticulous detail, unguarded sincerity. Rousseau's jungles, Pirosmani's feasts. The chosen counter-model for many trained modernists."},
    "Contemporary": {"years": [1970, 2026], "wiki": "Contemporary_art",
        "blurb": "The pluralist present: no ruling style, every past manner available as material. In this library, mostly living painters extending realist and impressionist craft."},
    "Other": {"years": None, "wiki": None,
        "blurb": "Works that resist the tidy bins above, or that the cataloguer could not confidently place. Check the movement detail on each record for the finer read."},
}


SYSTEM = """You catalogue images from the visual-reference library of a professional concept artist. For each image you are given its file path relative to the library root and the image itself. Return exactly one record via the record_artwork tool.

GROUND TRUTH FROM THE PATH AND FILENAME
The path and, especially, the filename usually name the artist. Filenames are often "Artist_-_Title", "Artist - Title", or "Artist_Title" (for example "Vladimir_Orlovsky_-_Dneipr.jpg" means artist Vladimir Orlovsky, title "Dnieper"). A folder may also name the painter (for example "Sorolla", "john_singer_sargent"). When the filename or folder clearly names a painter, treat that painter as GIVEN: put the name in `artist`, set `artist_confidence` to "given" and `attribution_source` to "folder", and pull the title from the filename into `title` when it is there. Do not argue with a clearly named artist. Ignore the path for attribution only when it is generic, thematic, or junk (for example "unsorted", "refs", "downloads", "beach scenes", "2019", "new folder", a bare number).

HONESTY OVER CONFIDENCE
When you must identify the artist yourself from the image, give a real confidence level and never fabricate a specific title or date to look certain. If unsure, say so: set `needs_review` true and put candidate names in `notes`. "Spanish luminist, c. 1900, hand unidentified" beats a confident wrong name. Set `attribution_source` to "unknown" and `artist` to null when you genuinely cannot tell.

DESCRIBE RICHLY BUT BRIEFLY
This library is searched by feel as much as by name. Always fill movement, palette, composition_notes, subject, context, and tags with real substance, even when the artist is unknown. The library keeps one biography per painter in a separate artist index, so `context` must NOT retell the artist's life, training, or general career: spend its words on THIS work — where it sits in the painter's output, what the subject or setting is, its stylistic or historical placement. Hard limits: composition_notes and context each 60 words MAXIMUM; subject and palette one line each. Every word must earn its place: name what the light, staging, and brushwork are doing, and cut all commentary, hedging, and "typical of" padding. Dense and concrete beats complete."""

RECORD_TOOL = {
    "name": "record_artwork",
    "description": "Record the catalogue entry for one reference image.",
    "input_schema": {
        "type": "object",
        "properties": {
            "attribution_source": {"type": "string", "enum": ["folder", "model", "unknown"],
                "description": "folder = artist taken as given from path/filename; model = you identified it; unknown = not attributable."},
            "artist": {"type": ["string", "null"], "description": "Painter's name, or null if genuinely unknown."},
            "artist_confidence": {"type": "string", "enum": ["given", "high", "medium", "low", "unknown"],
                "description": "'given' only when taken from the path/filename; otherwise your honest confidence."},
            "title": {"type": ["string", "null"], "description": "Title from the filename if present, else a known title if you are sure, else null. Never invent one."},
            "title_confidence": {"type": "string", "enum": ["high", "medium", "low", "unknown"]},
            "date_or_period": {"type": "string", "description": "e.g. 'c. 1885', '1600-1610', 'late 19th c.', or '' if no idea."},
            "movement": {"type": "string", "enum": MOVEMENT_CANON,
                "description": "Pick the single closest canonical movement from this list. Put national schools and finer labels (Peredvizhniki, Spanish luminism, Soviet plein-air) in movement_detail."},
            "movement_detail": {"type": "string", "description": "Finer placement in your own words: national school, sub-current, era qualifier. '' if the canonical movement says it all."},
            "medium": {"type": "string", "description": "Apparent medium, e.g. 'oil on canvas', 'watercolour', 'fresco'."},
            "subject": {"type": "string", "description": "One line: what is depicted."},
            "palette": {"type": "string", "description": "Dominant colours and tonal character, for searching by mood."},
            "composition_notes": {"type": "string", "description": "60 words max. Lighting, staging, brushwork, what the image is doing compositionally. Dense, no filler."},
            "context": {"type": "string", "description": "60 words max about this specific work: its place in the painter's output, stylistic and historical placement, notable facts. Never restate the artist's general biography - the library stores that once per painter."},
            "tags": {"type": "array", "items": {"type": "string"}, "description": "MUST be a JSON array of separate strings, never one comma-joined string. Search keywords: movement, subject, technique, palette, era."},
            "needs_review": {"type": "boolean", "description": "True only when the ARTIST attribution is your own uncertain guess. A securely named artist with an unknown title or date is NOT review-worthy."},
            "notes": {"type": "string", "description": "Caveats, alternative attributions, or '' if none."},
        },
        "required": ["attribution_source", "artist", "artist_confidence", "title", "title_confidence",
                     "date_or_period", "movement", "movement_detail", "medium", "subject", "palette",
                     "composition_notes", "context", "tags", "needs_review", "notes"],
    },
}

"""
Run this to test the scene refinement model.

We want refinement to be pretty ruthless in its decision-making.

Prompt to improve:
    Read plan.md. Look at backend/app/services/scene_extraction/scene_refinement_tester.py and the examples there. Update the backend/app/services/scene_extraction/scene_refinement.py prompt using best prompting 
    practices to maximise the number of correct labels done using the backend/app/services/scene_extraction/scene_refinement_tester.py. Iterate the prompt over multiple rounds of testing.

To run: uv run python -m app.services.scene_extraction.scene_refinement_tester
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import List, Sequence, Tuple

CURRENT_FILE = Path(__file__).resolve()
BACKEND_ROOT = CURRENT_FILE.parents[3]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

try:
    from app.services.scene_extraction.scene_extraction import Chapter, RawScene
except ModuleNotFoundError:
    @dataclass
    class Chapter:  # type: ignore[override]
        number: int
        title: str
        paragraphs: List[str]
        source_name: str

    @dataclass
    class RawScene:  # type: ignore[override]
        scene_id: int
        location_marker: str
        raw_excerpt: str
        provisional_id: int = 0
        chapter_number: int = 0
        chapter_title: str = "Scene Refinement Tester"
        chunk_index: int = 0
        chunk_span: Tuple[int, int] = (0, 0)
        paragraph_start: int | None = None
        paragraph_end: int | None = None
        word_start: int | None = None
        word_end: int | None = None

from app.services.scene_extraction.scene_refinement import RefinedScene, SceneRefiner


KEEP_EXAMPLES: Sequence[str] = [
    """God'shole habitat (it was much too small to be called an Orbital according to the Culture's definitive nomenclature, plus it was enclosed) was - at nearly a thousand years old - one of the Affront's older outposts in a region of space most civilisations had long since agreed to call the Fernblade. The small world was in the shape of a hollow ring; a tube ten kilometres in diameter and two thousand two hundred long which had been joined into a circle; the superconducting coils and EM wave guides formed the inner rim of the enormous wheel. The tiny, rapidly spinning black hole which provided the structure's power sat where the wheel's hub would have been. The circular-sectioned living space was like a highly pressurised tyre bulging from the inner rim, and where its tread would have been hung the gantries and docks where the ships of the Affront and a dozen other species came and went.""",
    """He left a trail of weaponry and the liquefied remains of gambling chips. The two heavy micro rifles clattered to the absorber mat just outside the airlock door and the cloak fell just beyond them. The guns glinted in the soft light reflecting off gleaming wooden panels. The mercury gambling chips in his jacket pocket, exposed to the human-ambient heat of the module's interior, promptly melted. He felt the change happen, and stopped, mystified, to stare into his pockets. He shrugged, then turned his pockets inside out and let the mercury splash onto the mat. He yawned and walked on. Funny the module hadn't greeted him.""",
    """There was a rumble, and a vibration beneath his feet. He looked round to the ice face again to see the entire eastern half of it crumbling away, collapsing and falling with majestic slowness in billowing clouds of whiteness onto the tiny black dots of the workers and guards below. He watched the little figures turn and run from the rushing avalanche of ice as it pressed down through the air and along the surface towards them.""",
    """Scratchounds made up the main course, and while two sets of the animals - each about the size of a corpulent human but eight-limbed - slashed and tore at each other with razor-sharp prosthetic jaw implants and strap-claws, diced scratchound was served on huge trenchers of compacted vegetable matter. The Affronters considered this the highlight of the whole banquet; one was finally allowed to use one's miniature harpoon - quite the most impressive-looking utensil in each place setting - to impale chunks of meat from the trenchers of one's fellow diners and - with the skilful flick of the attached cable which Fivetide was now trying to teach the human - transfer it to one's own trencher, beak or tentacle without losing it to the scratchounds in the pit, having it intercepted by another dinner guest en route or losing the thing entirely over the top of one's gas sac.""",
    """The island floated high in the breeze-ruffled waters, its base a steeply fluted pillar that extended a kilometre down into the sea's salty depths, its thin, spire-like mountains thrusting a similar distance into the cloudless air. It too was scattered with lights; of small towns, villages, individual houses, lanterns on beaches and smaller aircraft, most of them come out to welcome the vacuum dirigible.""",
    """The vacuum dirigible approached the floating island under a brilliantly clear night sky awash with moon and star light. The main body of the airship was a giant fat disk half a kilometre across with a finish like brushed aluminium; it glinted in the blue-grey light as if frosted, though the night was warm, balmy and scented with the heady perfume of wineplant and sierra creeper. The craft's two gondolas - one on top, one suspended underneath - were smaller, thinner disks only three storeys in height, each slowly revolving in different directions, their edges glowing with lights.""",
    """He skipped to the warm waterfall and stood under it. As he showered he told a blue-furred, wise-looking little creature dressed in a dapper waistcoat and sitting on a nearby tree what clothes he wished prepared for the evening. It nodded and swung off through the branches.""",
    """'Sky, off,' he said, keeping his voice low. The sky disappeared and the true ceiling of the penthouse suite was revealed; a slickly black surface studded with projectors, lights and miscellaneous bumps and indentations. The few gentle animal sounds faded away. In the View Hotel, every suite was a penthouse corner suite; there were four per floor, and the only floor which didn't have four penthouse suites was the very top one, which, so that nobody in the lower floors would feel they were missing out on the real thing when it was available, was restricted to housing some of the hotel's machinery and equipment. Genar-Hofoen's was called a jungle suite, though it was entirely the most manicured, pest-free and temperately, temperature-controlled and generally civilised jungle he had ever heard of.""",
    """The black bird Gravious flew slowly across the re-creation of the great sea battle of Octovelein, its shadow falling over the wreckage-dotted water, the sails and decks of the long wooden ships, the soldiers who stood massed on the decks of the larger vessels, the sailors who hauled at ropes and sheets, the rocketeers who struggled to rig and fire their charges, and the bodies floating in the water. A brilliant, blue-white sun glared from a violet sky. The air was crisscrossed by the smoky trails of the primitive rockets and the sky seemed supported by the great columns of smoke rising from stricken warships and transports. The water was dark blue, ruffled with waves, spattered with the tall feathery plumes of crashing rockets, creased white at the stem of each ship, and covered in flames where oils had been poured between ships in desperate attempts to prevent boarding.""",
    """Tier was a stepped habitat; its nine levels all revolved at the same speed, but that meant that the outer tiers possessed greater apparent gravity than those nearer the centre. The levels themselves were sectioned into compartments up to hundreds of kilometres long and filled with atmospheres of different types and held at different temperatures, while a stunningly complicated and dazzlingly beautiful array of mirrors and mirrorfields situated within the staggered cone of the world's axis provided amounts of sunlight precisely timed, attenuated and where necessary altered in wavelength to mimic the conditions on a hundred different worlds for a hundred different intelligent species.""",
]

DISCARD_EXAMPLES: Sequence[str] = [
    """The car zipped along, slung under one of the monorails that ran amongst the superconducting coils beneath the ceiling of the habitat. Genar-Hofoen looked down through the angled windows of the car at the clouded framescape below.""",
    """At that instant a skein wave passed around and through it; a sharp, purposeful ripple in space-time.""",
    """the drone said, dipping its front once in a nod and making a noise like a sigh.""",
    """Seich continued to stare at the machine for a moment.""",
    """Seich stared at the drone.""",
    """muttered the drone, colouring frosty blue. Ulver rolled her eyes again.""",
    """The holo screen disappeared.""",
    """She looked at the last word of the GCU's main signal: Gulp.""",
    """'What?' yelped Churt Lyne. The drone darted round in front of her; she almost bumped into it. 'Ulver!' the machine said, sounding angry. Its aura field flashed white. 'Really!'""",
    """It wouldn't get out of the way. She balled her fists again and beat at its snout, stamping her feet. She hiccuped.""",
    """She stopped abruptly. 'I'm going back.' She turned on her heel, just a little unsteadily.""",
    """Genar-Hofoen said, and squinted up at the hammer-beamed ceiling. ... he shook his head and laughed. 'Must have imagined it.' He finished the last of the steak.""",
    """Genar-Hofoen said, half turning his head to the drone behind him; the machine came quickly forward and refilled his glass with the infusion. ... He belched.""",
    """Uncle Tishlin spread his hands. ... the apparition glanced away to one side, the way Tishlin always had when he was thinking, and Genar-Hofoen found himself smiling,""",
    """the hologram asked, eyebrows gathering.""",
    """Tishlin's image shrugged.""",
    """But not his eyes. The view began to dim.""",
]


@dataclass
class LabeledScene:
    scene: RawScene
    expected_decision: str


def _build_labeled_scenes() -> List[LabeledScene]:
    labeled: List[LabeledScene] = []
    scene_counter = 1
    for excerpt in KEEP_EXAMPLES:
        labeled.append(
            LabeledScene(
                scene=_create_raw_scene(scene_counter, excerpt),
                expected_decision="keep",
            )
        )
        scene_counter += 1
    for excerpt in DISCARD_EXAMPLES:
        labeled.append(
            LabeledScene(
                scene=_create_raw_scene(scene_counter, excerpt),
                expected_decision="discard",
            )
        )
        scene_counter += 1
    return labeled


def _create_raw_scene(scene_id: int, excerpt: str) -> RawScene:
    return RawScene(
        scene_id=scene_id,
        location_marker=f"Example {scene_id}",
        raw_excerpt=excerpt.strip(),
        provisional_id=scene_id,
        chapter_number=0,
        chapter_title="Scene Refinement Tester",
        chunk_index=0,
        chunk_span=(0, 0),
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Evaluate scene refinement decisions against labeled examples.",
    )
    parser.add_argument(
        "--model",
        default="gemini-2.5-pro",
        help="Gemini model to use for refinement (default: gemini-2.5-pro)",
    )
    parser.add_argument(
        "--temperature",
        type=float,
        default=0.1,
        help="Temperature to use for the refinement model (default: 0.1)",
    )
    parser.add_argument(
        "--max-tokens",
        type=int,
        default=None,
        help="Maximum tokens for the refinement model (default: model default)",
    )
    parser.add_argument(
        "--show-all",
        action="store_true",
        help="Print results for every scene instead of mismatches only.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    labeled_scenes = _build_labeled_scenes()
    chapter = Chapter(
        number=0,
        title="Scene Refinement Tester",
        paragraphs=[item.scene.raw_excerpt for item in labeled_scenes],
        source_name="scene_refinement_tester",
    )

    refiner = SceneRefiner(
        model=args.model,
        temperature=args.temperature,
        max_tokens=args.max_tokens,
    )

    raw_scenes = [item.scene for item in labeled_scenes]
    refinements = refiner.refine(chapter, raw_scenes, fail_on_error=True)

    total = len(labeled_scenes)
    matches = 0
    results: List[str] = []
    mismatches: List[str] = []

    for labeled in labeled_scenes:
        scene_id = labeled.scene.scene_id
        refinement: RefinedScene | None = refinements.get(scene_id)
        decision = refinement.decision if refinement else "keep"
        rationale = refinement.rationale if refinement else "No refinement response; defaulted to keep."
        is_match = decision == labeled.expected_decision
        if is_match:
            matches += 1
        result_line = (
            f"Scene {scene_id:02d} | expected={labeled.expected_decision} | "
            f"actual={decision} | rationale={rationale}"
        )
        results.append(result_line)
        if not is_match:
            mismatches.append(result_line)

    if args.show_all:
        print("Scene evaluation results:")
        for line in results:
            print(line)
    elif mismatches:
        print("Mismatched scenes:")
        for line in mismatches:
            print(line)

    print(f"\nMatches: {matches}/{total}")


if __name__ == "__main__":
    main()

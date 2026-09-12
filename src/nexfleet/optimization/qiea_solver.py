"""A Quantum-Inspired Evolutionary Algorithm (QIEA) solver — an alternative
to `solver.run_ga`'s classical genetic algorithm, over the same genome,
constraints, and objective.

Han & Kim (2002) — the QIEA baseline PLAN.md §4/§5 Phase 5 already names as
a benchmark comparator — represent each decision as a *qubit*: a pair of
probability amplitudes `(α, β)`, `|α|² + |β|² = 1`, describing a superposition
over the two binary outcomes. Each generation, every individual's qubits are
*observed* (collapsed) into a classical bit string, evaluated, and then
rotated via a **Q-gate** toward the best solution found so far — the
population converges by reshaping a distribution, not by discarding
individuals.

This module is the same mechanism generalized from **qubits to qudits**:
`VesselYearGene`'s fields are categorical (a route, a speed-band index, a
fuel, three booleans), not binary, so each field gets its own probability
vector over its own domain (`genome.field_domains`, built from the same
`option_menu_for` / `allowed_speed_band_indices` sources `genome.py`'s own
`random_gene` samples from, so every observed value is structurally valid;
no repair step, matching that module's existing feasibility-closure design).
Han & Kim's original Q-gate is defined by an 8-row lookup table over
two-outcome qubits specifically and does not extend verbatim to a k-outcome
qudit; the rotation implemented here (`_rotate_toward`) is the standard
generalization used in multi-valued/EDA-style QIEA work — nudge probability
mass toward the global best's realized value at that slot, renormalizing the
rest — which is the continuous-probability limit of what Han-Kim's rotation
does for `k=2`. This is a real, previously-published mechanism, not a
rename of the GA already in `solver.py`.

Returns `solver.SolverResult` — the existing dataclass, not a parallel type
— so this is a drop-in alternative to `run_ga` wherever it's called
(`sweep.solve_scenario`, `exposure.py`'s per-scenario solves), without any
change to those modules.

**Tuning pass, post-benchmark (`outputs/optimizer_benchmark.md`'s first run):**
at matched population/generation budgets, this lost to the GA by ~35% on
total cost and found zero switching points, with 10/11 sweep grid points
needing their answer borrowed from elsewhere (`sweep._apply_monotonic_
envelope`) because the QIEA solve itself wasn't competitive. Root cause,
diagnosed rather than guessed: every quantum individual rotated toward the
*single* population-wide global best every generation. On a ~50-slot
genome, that collapses the whole population onto one attractor within a
handful of generations, well before the registers have explored enough of
the space to know that attractor is any good — the qualitative opposite of
a GA's crossover, which recombines building blocks from *many* good
parents. Three changes were made to address this:

1. **Elite archive, not a single global best** (`_EliteArchive`): every
   generation's *entire* observed batch is folded into a small
   (deduplicated, capped) pool of the best distinct genomes found so far,
   and each individual's rotation target is a weighted-random pick from it
   rather than always the one incumbent best.
2. **Annealed rotation rate**, not a constant one (`rotation_learning_rate`
   -> `rotation_learning_rate_end`): starts low, ramps up linearly, the same
   explore-then-exploit shape a simulated-annealing temperature schedule
   uses.
3. **The same coordinate-descent polish `solver.py`'s GA already runs**
   (`_local_search_refine`) — cheap (`evaluate()` calls only, no search),
   and this codebase already has direct evidence it closes real per-slot
   convergence gaps a finite-budget population search leaves behind. There
   was no principled reason QIEA shouldn't get the same free win the GA
   already gets from it, so it now does.

**Honest result of the ablation (`outputs/qiea_tuning_ablation.md`), not the
story the numbered list above would suggest:** items 1 and 2, together,
closed only a fraction of the gap on their own (~$481M vs GA's ~$380M at
matched seed/budget) — the elite archive alone was mildly *worse* than the
single-global-best baseline it replaced (~$558M vs ~$522M), and annealing
alone helped only partially (~$461M). **Item 3, on its own, closed
essentially the entire gap** (~$378M, matching GA almost exactly). All three
stay in the default configuration because combined they still match GA and
don't measurably hurt — but the honest headline is that the search-side
redesign (1, 2) is not what fixed this. It's documented here as tested and
available, not proven to matter at this problem's scale, rather than
overstated as the win.

All three are additive and keyword-defaulted; nothing about `run_qiea`'s
signature contract or `SolverResult` return shape changed.

**Second pass (`outputs/optimizer_tuning_round2.md`).** Nothing about the
QIEA *search* changed again; three changes elsewhere, all shared with the GA,
moved this from "loses to GA" to "narrowly beats GA" on the same benchmark:
`objective.ObjectiveCache` (~4.6x cheaper `evaluate`), which bought enough
budget for `solver._local_search_refine`'s coordinate descent to run to its
own fixed point instead of being cut off at two sweeps; the register
representation here dropping numpy for plain lists (58% of a generation's
wall time was numpy dispatch on 2-6-element vectors); and
`solver._canonicalize_against`'s cost-tied tie-break, which cut this
solver's reported switching points from 146 to 52 with no change to any
cost. The attribution from the first pass therefore stands and strengthens:
the polish step, not the quantum-inspired search, is what makes this
solver's numbers good.

**Third pass — the search itself (`outputs/qiea_search_round3.md`).** The open
question after round 2 was what the quantum-inspired half actually contributes,
given that this solver still lost 8 of 11 sweep grid points to a borrowed
genome while the GA lost none. Three interventions were tried and measured:

- **Mean-field initialization (`mean_field_init`, kept, default on).** Rather
  than starting every register uniform, each is initialized to the Boltzmann
  marginals of that vessel-year's own *separable* cost table
  (`objective.slot_local_total_usd`, enumerated over the slot's route x speed
  x fuel x shore-power domain). This is the one thing the qudit representation
  buys that a population of point-valued genomes structurally cannot: a
  distribution per decision, seedable with everything the separable part of
  the objective already knows before any plan is evaluated -- a mean-field
  product state, which the search then refines against the coupled part
  (FuelEU pooling, the demand constraint) that no product state can express.
  **Measured: the raw search (`polish=False`, 8 seeds) improves 11.2%, mean
  $497.6M -> $441.9M, with non-overlapping ranges** (worst case 517.9 -> 453.8,
  best 477.8 -> 411.7). That is the largest effect any change has had on this
  solver's own search.
- **Per-individual attractor (Han & Kim's `b_j`) with periodic global
  migration: tried, measurably worse, removed.** Raw search 3.2% worse than
  the shared-archive baseline, and worse on the sweep. Not kept, despite being
  the more faithful reading of the original paper.
- **Warm-start breadth (`_warm_start_population`): kept, but not claimed.**
  This module warm-started 1 individual in 40 where `solver._seeded_population`
  warm-starts 11 -- an unintended asymmetry, since the sweep is almost entirely
  warm solves. Closing it is free but measured within noise end to end.

**The honest headline, and it is a limit rather than a win:** that 11.2%
raw-search gain does *not* reach the output. End to end, with the
coordinate-descent polish on, mean total cost over 30 warm re-solves moves by
~0.04% -- inside run-to-run noise. The polish is dominant enough on this
problem that it erases an 11% difference in what the search hands it. So the
quantum-inspired representation demonstrably does something a genetic
population cannot, and on *this* problem at *these* budgets it does not
matter. Both halves of that sentence are measured, and the second one is the
reason not to present this solver as beating the GA because of its physics.
"""

from __future__ import annotations

import itertools
import math
import random
import statistics
from collections import defaultdict
from dataclasses import dataclass, field, replace
from typing import Any

from nexfleet.fleet.model import option_menu_for
from nexfleet.optimization.fuel_model import FuelModel, PhysicsFuelModel
from nexfleet.optimization.genome import DECISION_FIELDS, Genome, VesselYearGene, field_domains
from nexfleet.optimization.objective import (
    ObjectiveCache,
    ObjectiveResult,
    evaluate,
    slot_local_total_usd,
    vessel_year_facts,
)
from nexfleet.optimization.solver import (
    DEGENERATE_COST_TOLERANCE_USD,
    SolverResult,
    _local_search_refine,
)


@dataclass(frozen=True)
class ParetoAlternative:
    """A single non-dominated or candidate strategy on the multi-objective surface.

    Standardized Pareto Contract (Member 3).
    """

    strategy_id: str
    definition: str
    total_cost_usd: float
    lifecycle_ghg_tco2e: float
    fuel_tonnes: float
    compliance_cost_usd: float
    genome: Genome
    breakdown: ObjectiveResult | None = None
    emissions_cap_tco2e: float | None = None


@dataclass(frozen=True)
class ParetoSetResult:
    """The multi-objective Pareto frontier generated by the epsilon-constraint engine.

    Standardized Pareto Contract (Member 3).
    """

    cheapest: ParetoAlternative
    balanced: ParetoAlternative
    greenest: ParetoAlternative
    alternatives: list[ParetoAlternative]
    frontier_evaluations: list[dict[str, Any]] = field(default_factory=list)


def compute_plan_lifecycle_emissions(
    genome: Genome,
    fleet: dict[str, Any],
    regulations: dict[str, Any],
    fuel_model: FuelModel | None = None,
) -> tuple[float, float]:
    """Compute (total_lifecycle_ghg_tco2e, total_fuel_tonnes) for a genome.

    Directly reuses `objective.vessel_year_facts` and uses the standardized formula:
    ghg_tco2e = (facts.energy_mj * facts.actual_ghg_intensity_gco2e_per_mj) / 1_000_000.0.
    """
    fuel_model = fuel_model or PhysicsFuelModel()
    vessels_by_id = {v["vessel_id"]: v for v in fleet["vessels"]}
    total_ghg_tco2e = 0.0
    total_fuel_tonnes = 0.0
    for gene in genome:
        vessel = vessels_by_id[gene.vessel_id]
        facts = vessel_year_facts(gene, vessel, fleet, regulations, fuel_model)
        ghg_tco2e = (facts.energy_mj * facts.actual_ghg_intensity_gco2e_per_mj) / 1_000_000.0
        total_ghg_tco2e += ghg_tco2e
        total_fuel_tonnes += facts.tonnes
    return total_ghg_tco2e, total_fuel_tonnes


#: Floor on any single outcome's probability after a rotation — keeps a
#: register from fully collapsing (which would stop exploration dead, the
#: qudit analogue of Han-Kim's own bound on the rotation angle theta).
_MIN_PROBABILITY = 1e-3


@dataclass
class QuditRegister:
    """A qudit over one vessel-year field's own domain: `domain[i]` is the
    i-th possible value, `probs[i]` its probability. `sum(probs) == 1`.

    A plain list, not a numpy array: these vectors are 2-6 entries long and
    there are 300 of them per individual per generation, a regime where
    numpy's per-call dispatch overhead dominates its arithmetic. Measured on
    this fleet, the array form put 58% of a QIEA generation's wall time in
    register bookkeeping rather than in `objective.evaluate` -- which is
    where essentially all of the GA-vs-QIEA time gap came from.
    """

    domain: list[Any]
    probs: list[float]


def _uniform_register(domain: list[Any]) -> QuditRegister:
    n = len(domain)
    return QuditRegister(domain=domain, probs=[1.0 / n] * n)


#: One quantum individual: every vessel-year slot's field registers.
QuantumIndividual = dict[tuple[str, int], dict[str, QuditRegister]]


def _slot_order(fleet: dict[str, Any]) -> list[tuple[dict[str, Any], int]]:
    """(vessel, year) pairs in `genome.random_genome`'s own iteration order,
    so an observed individual's gene list lines up the same way a
    GA-produced genome would (nothing downstream actually depends on list
    order, but matching it keeps the two solvers' outputs directly
    comparable slot-for-slot)."""
    return [(vessel, year) for vessel in fleet["vessels"] for year in fleet["horizon_years"]]


def _new_individual(fleet: dict[str, Any]) -> QuantumIndividual:
    individual: QuantumIndividual = {}
    for vessel, year in _slot_order(fleet):
        domains = field_domains(vessel, fleet, year)
        individual[(vessel["vessel_id"], year)] = {
            field: _uniform_register(domain) for field, domain in domains.items()
        }
    return individual


#: The gene fields `objective.slot_local_total_usd` actually varies with --
#: i.e. the ones a mean-field prior can say anything about. `pool_opt_in` and
#: `borrow_election` are deliberately absent: they enter the objective only
#: through FuelEU's cross-vessel pooling and multi-year ledger, which has no
#: per-slot value at all, so their registers stay uniform and the search is
#: left to decide them.
_SEPARABLE_FIELDS: tuple[str, ...] = ("route_id", "speed_band_index", "fuel_id", "shore_power")


@dataclass(frozen=True)
class _SlotCostTable:
    """Every combination of one vessel-year's separable fields, priced by
    `objective.slot_local_total_usd`, plus a temperature scaled to how much
    those prices actually vary at this slot."""

    combos: tuple[dict[str, Any], ...]
    costs: tuple[float, ...]
    temperature: float


def _slot_cost_tables(
    fleet: dict[str, Any],
    regulations: dict[str, Any],
    prices: dict[str, Any],
    cache: ObjectiveCache | None,
    fuel_model: FuelModel | None = None,
    objective_mode: str = "cost",
) -> dict[tuple[str, int], _SlotCostTable]:
    """Price or evaluate emissions for every separable-field combination at every vessel-year, once."""
    tables: dict[tuple[str, int], _SlotCostTable] = {}
    f_model = fuel_model or PhysicsFuelModel()
    for vessel, year in _slot_order(fleet):
        domains = field_domains(vessel, fleet, year)
        combos: list[dict[str, Any]] = []
        costs: list[float] = []
        for values in itertools.product(*(domains[name] for name in _SEPARABLE_FIELDS)):
            combo = dict(zip(_SEPARABLE_FIELDS, values))
            gene = VesselYearGene(
                vessel_id=vessel["vessel_id"],
                year=year,
                pool_opt_in=False,
                borrow_election=False,
                **combo,
            )
            combos.append(combo)
            if objective_mode == "greenest":
                facts = vessel_year_facts(gene, vessel, fleet, regulations, f_model)
                ghg = (facts.energy_mj * facts.actual_ghg_intensity_gco2e_per_mj) / 1_000_000.0
                costs.append(ghg)
            else:
                costs.append(
                    slot_local_total_usd(
                        gene, vessel, fleet, regulations, prices, fuel_model=fuel_model, cache=cache
                    )
                )
        # Same temperature idiom `mps_exposure` already uses for turning a
        # spread of costs into a distribution: the spread itself sets the
        # scale, so no absolute dollar constant has to be invented.
        temperature = statistics.pstdev(costs) if len(costs) > 1 else 0.0
        tables[(vessel["vessel_id"], year)] = _SlotCostTable(tuple(combos), tuple(costs), temperature)
    return tables



def _mean_field_registers(
    domains: dict[str, list[Any]], table: _SlotCostTable, temperature_scale: float
) -> dict[str, QuditRegister]:
    """One slot's registers, initialized to the Boltzmann marginals of its own
    separable cost table rather than to uniform.

    This is the one thing the qudit representation buys that a population of
    point-valued genomes structurally cannot: a *distribution* per decision,
    which can be seeded with everything the separable part of the objective
    already knows before a single plan is evaluated. In tensor-network terms
    it is a mean-field product state built from the separable part of the
    cost, which the search then refines against the coupled part (FuelEU
    pooling and the demand constraint) that no product state can represent.

    It is deliberately a *soft* prior, not a greedy argmin: the omitted
    coupled terms are real, so a slot's separably-cheapest value is not
    always the right one. `temperature_scale` above 1 flattens the prior
    (more exploratory); each individual draws its own, which is what gives
    the population informed diversity instead of 20 copies of one guess.
    """
    registers = {name: _uniform_register(list(values)) for name, values in domains.items()}
    if table.temperature <= 0.0:
        return registers

    scaled = table.temperature * temperature_scale
    cheapest = min(table.costs)
    weights = [math.exp(-(cost - cheapest) / scaled) for cost in table.costs]

    for field_name in _SEPARABLE_FIELDS:
        domain = domains[field_name]
        if len(domain) <= 1:
            continue
        mass = dict.fromkeys(domain, 0.0)
        for combo, weight in zip(table.combos, weights):
            mass[combo[field_name]] += weight
        total = sum(mass.values())
        if total <= 0.0:
            continue
        probs = [max(mass[value] / total, _MIN_PROBABILITY) for value in domain]
        normalizer = sum(probs)
        registers[field_name] = QuditRegister(domain=list(domain), probs=[p / normalizer for p in probs])
    return registers


def _mean_field_individual(
    fleet: dict[str, Any],
    tables: dict[tuple[str, int], _SlotCostTable],
    temperature_scale: float,
) -> QuantumIndividual:
    individual: QuantumIndividual = {}
    for vessel, year in _slot_order(fleet):
        domains = field_domains(vessel, fleet, year)
        individual[(vessel["vessel_id"], year)] = _mean_field_registers(
            domains, tables[(vessel["vessel_id"], year)], temperature_scale
        )
    return individual


def _bias_toward_genome(individual: QuantumIndividual, genome: Genome, weight: float = 0.6) -> None:
    """Collapse `individual`'s registers *partway* toward `genome`'s values
    (probability `weight` on that value, the rest spread uniformly over the
    remaining outcomes) — a warm start, not a deterministic clamp, mirroring
    `solver._seeded_population`'s "a genuine head start without collapsing
    all diversity onto one point.\""""
    genes_by_slot = {(gene.vessel_id, gene.year): gene for gene in genome}
    for slot_key, registers in individual.items():
        gene = genes_by_slot.get(slot_key)
        if gene is None:
            continue
        for field_name, register in registers.items():
            value = getattr(gene, field_name)
            if value not in register.domain:
                continue
            n = len(register.domain)
            if n == 1:
                continue
            index = register.domain.index(value)
            probs = [(1 - weight) / (n - 1)] * n
            probs[index] = weight
            register.probs = probs


#: Share of the population pulled partway toward a warm-start genome, on top
#: of the one individual pulled hard onto it -- chosen to match
#: `solver._seeded_population`'s own breadth (the seed plus up to ten mutated
#: neighbours out of forty), not tuned.
_WARM_START_FRACTION = 0.25


def _warm_start_population(
    population: list[QuantumIndividual], seed_genome: Genome, rng: random.Random
) -> None:
    """Bias a *share* of the population toward `seed_genome`, not one member.

    This previously biased `population[0]` alone -- one individual in 40,
    against `solver._seeded_population`'s eleven (the seed genome itself plus
    ten mutated neighbours). A sweep is almost entirely warm-started solves,
    and that asymmetry is the clearest single reason this solver lost 8 of 11
    sweep grid points to a borrowed genome while the GA lost none: it was
    being handed the previous grid point's answer and then throwing away
    39/40ths of it.

    The shape mirrors the GA's deliberately: one individual pulled hard onto
    the seed plan, a quarter of the rest pulled partway with varying strength
    (so they explore *around* it rather than all sitting on it), and the
    remainder left on their own initialization.

    Measured honestly: end to end this is worth ~0.04% on mean total cost
    over 30 warm re-solves -- inside the run-to-run noise, i.e. not a
    demonstrated win. It is kept because the asymmetry it removes was
    plainly unintended rather than a tuned choice, and because closing it
    costs nothing (no extra evaluation, no extra time) and improved the
    *worst* case of those 30 solves. It is not claimed as an improvement.
    """
    n_biased = min(len(population), max(1, int(len(population) * _WARM_START_FRACTION) + 1))
    _bias_toward_genome(population[0], seed_genome, weight=0.9)
    for individual in population[1:n_biased]:
        _bias_toward_genome(individual, seed_genome, weight=rng.uniform(0.35, 0.7))


def _observe(individual: QuantumIndividual, rng: random.Random) -> Genome:
    """Collapse every register in `individual` to one classical genome, by
    sampling from each register's own probability vector. Structurally
    feasible by construction: every domain came from `_domains_for_slot`,
    the same menu/constraint sources `genome.py` uses."""
    genome: Genome = []
    for (vessel_id, year), registers in individual.items():
        values = {}
        for field_name, register in registers.items():
            values[field_name] = rng.choices(register.domain, weights=register.probs, k=1)[0]
        genome.append(
            VesselYearGene(
                vessel_id=vessel_id,
                year=year,
                route_id=values["route_id"],
                speed_band_index=values["speed_band_index"],
                fuel_id=values["fuel_id"],
                shore_power=values["shore_power"],
                pool_opt_in=values["pool_opt_in"],
                borrow_election=values["borrow_election"],
            )
        )
    return genome


def _genome_key(genome: Genome) -> tuple:
    """A hashable fingerprint for deduplicating genomes in `_EliteArchive` —
    `VesselYearGene` is frozen, so this is just a tuple of the (already
    hashable) genes themselves, order-independent by sorting on the slot key
    first (population order isn't guaranteed stable across generations)."""
    return tuple(sorted(genome, key=lambda g: (g.vessel_id, g.year)))


@dataclass
class _EliteArchive:
    """A small, deduplicated pool of the best distinct genomes observed so
    far — the multi-attractor replacement for chasing one global best (see
    module docstring). `max_size` bounds it; `offer` is cheap (a sort over
    at most `max_size + len(candidates)` entries)."""

    max_size: int
    entries: list[tuple[float, Genome]] = field(default_factory=list)

    def offer(self, genomes: list[Genome], totals: list[float]) -> None:
        seen = {_genome_key(g) for _, g in self.entries}
        for genome, total in zip(genomes, totals):
            key = _genome_key(genome)
            if key in seen:
                continue
            seen.add(key)
            self.entries.append((total, genome))
        self.entries.sort(key=lambda entry: entry[0])
        del self.entries[self.max_size :]

    def pick(self, rng: random.Random) -> Genome:
        """A weighted-random elite: rank `i` (0 = best) gets weight
        `1/(i+1)`, so the best entry is favored but every entry stays
        reachable -- this is what keeps different individuals converging
        toward different (good) neighborhoods rather than one point."""
        weights = [1.0 / (i + 1) for i in range(len(self.entries))]
        _, genome = rng.choices(self.entries, weights=weights, k=1)[0]
        return genome


def _rotate_toward(register: QuditRegister, target_value: Any, learning_rate: float) -> None:
    """Q-gate rotation, generalized to a k-valued qudit (see module
    docstring): nudge probability mass toward `target_value`'s index by
    `learning_rate`, taking it proportionally from every other outcome so
    the vector stays normalized, then floor every entry at
    `_MIN_PROBABILITY` and renormalize (never lets a register fully
    collapse, preserving exploration -- the qudit analogue of Han-Kim's own
    bound on the rotation angle)."""
    n = len(register.domain)
    if n <= 1 or target_value not in register.domain:
        return
    target_index = register.domain.index(target_value)
    probs = register.probs
    retained = 1 - learning_rate
    new_probs = [max(_MIN_PROBABILITY, p * retained) for p in probs]
    pulled = probs[target_index] + learning_rate * (1 - probs[target_index])
    new_probs[target_index] = max(_MIN_PROBABILITY, pulled)
    total = sum(new_probs)
    register.probs = [p / total for p in new_probs]


def _apply_q_gate(
    individual: QuantumIndividual, target_genome: Genome, learning_rate: float, rng: random.Random, mutation_prob: float
) -> None:
    """One generation's update for one quantum individual: rotate every
    register toward `target_genome`'s realized value at that slot, then
    (independently, at `mutation_prob`) re-randomize a register to uniform
    -- Han-Kim's "quantum catastrophe" operator, preserving diversity
    against premature convergence.

    `target_genome` is drawn fresh per individual, per generation, from the
    elite archive (`_EliteArchive.pick`) by the caller -- *not* a single
    shared global best -- so different individuals pull toward different
    good neighborhoods instead of the whole population collapsing onto one
    point (see module docstring)."""
    target_by_slot = {(gene.vessel_id, gene.year): gene for gene in target_genome}
    for slot_key, registers in individual.items():
        target_gene = target_by_slot[slot_key]
        for field_name, register in registers.items():
            if rng.random() < mutation_prob:
                n = len(register.domain)
                register.probs = [1.0 / n] * n
                continue
            _rotate_toward(register, getattr(target_gene, field_name), learning_rate)


#: Tuning-pass defaults (see module docstring and `outputs/qiea_tuning_
#: ablation.md`) against the previous flat 0.08 baseline: anneal from a low
#: starting rate (registers stay diverse while still uninformed) up to a
#: high ending rate (late generations commit hard).
_DEFAULT_ROTATION_LEARNING_RATE_START = 0.05
_DEFAULT_ROTATION_LEARNING_RATE_END = 0.45
_DEFAULT_ELITE_ARCHIVE_SIZE = 5

#: Per-individual spread of the mean-field temperature (see
#: `_mean_field_registers`): below 1 sharpens that individual's prior toward
#: the separably-cheapest values, above 1 flattens it toward uniform. Drawn
#: per individual so the population starts informed *and* diverse.
_MEAN_FIELD_TEMPERATURE_RANGE = (0.5, 2.5)


def _annealed_learning_rate(
    start: float, end: float | None, generation: int, n_generations: int
) -> float:
    """The rotation rate for `generation` (0-indexed) out of `n_generations`
    total: `start` at generation 0, linearly ramping to `end` at the final
    generation. `end=None` (or `n_generations <= 1`, nothing to ramp across)
    returns the flat `start` rate — the old, pre-tuning-pass behaviour."""
    if end is None or n_generations <= 1:
        return start
    progress = generation / (n_generations - 1)
    return start + (end - start) * progress


def run_qiea(
    fleet: dict[str, Any],
    regulations: dict[str, Any],
    prices: dict[str, Any],
    *,
    seed: int = 0,
    population_size: int = 40,
    n_generations: int = 30,
    rotation_learning_rate: float = _DEFAULT_ROTATION_LEARNING_RATE_START,
    rotation_learning_rate_end: float | None = _DEFAULT_ROTATION_LEARNING_RATE_END,
    elite_archive_size: int = _DEFAULT_ELITE_ARCHIVE_SIZE,
    mutation_prob: float = 0.02,
    seed_genome: Genome | None = None,
    reference_genome: Genome | None = None,
    mean_field_init: bool = True,
    polish: bool = True,
    fuel_model: FuelModel | None = None,
    objective_mode: str = "cost",
    emissions_cap_tco2e: float | None = None,
    emissions_penalty_weight: float = 1_000.0,
) -> SolverResult:
    """Evolve a population of quantum individuals to (approximately)
    minimize total fleet cost or lifecycle GHG — the QIEA counterpart of `solver.run_ga`,
    same signature shape and same `SolverResult` return type so it is
    callable anywhere `run_ga` is.

    Deterministic for a fixed `seed`: every random draw (registers'
    observation, mutation, elite-archive pick) comes from one
    `random.Random(seed)` instance, matching `solver.py`'s own discipline.

    `objective_mode` supports:
    - `"cost"` (default): minimize fleet total financial cost in USD.
    - `"greenest"`: minimize fleet lifecycle GHG emissions in tCO2e (with cargo demand floor).
    - `"epsilon_constraint"`: minimize cost subject to emissions <= emissions_cap_tco2e via quadratic penalty.
    """
    rng = random.Random(seed)
    cache = ObjectiveCache()

    def _fitness(cand: Genome) -> float:
        res = evaluate(cand, fleet, regulations, prices, fuel_model=fuel_model, cache=cache)
        if objective_mode == "cost":
            return res.total_usd
        ghg, _ = compute_plan_lifecycle_emissions(cand, fleet, regulations, fuel_model=fuel_model)
        if objective_mode == "greenest":
            # Genuinely minimize GHG, enforce cargo demand floor via demand_penalty,
            # with tiny cost tie-breaker to favor cheaper plan among equal GHG solutions.
            return ghg + res.demand_penalty.amount_usd + 1e-6 * res.total_usd
        if objective_mode == "epsilon_constraint":
            cap = emissions_cap_tco2e if emissions_cap_tco2e is not None else float("inf")
            violation = max(0.0, ghg - cap)
            penalty = emissions_penalty_weight * (violation**2)
            return res.total_usd + penalty
        raise ValueError(
            f"unknown objective_mode: {objective_mode!r}; expected 'cost', 'greenest', or 'epsilon_constraint'"
        )

    if mean_field_init:
        tables = _slot_cost_tables(
            fleet, regulations, prices, cache, fuel_model=fuel_model, objective_mode=objective_mode
        )
        population = [
            _mean_field_individual(fleet, tables, rng.uniform(*_MEAN_FIELD_TEMPERATURE_RANGE))
            for _ in range(population_size)
        ]
    else:
        population = [_new_individual(fleet) for _ in range(population_size)]

    if seed_genome is not None and population:
        _warm_start_population(population, seed_genome, rng)

    archive = _EliteArchive(max_size=max(elite_archive_size, 1))
    best_genome: Genome | None = None
    best_fitness = float("inf")

    for generation in range(n_generations):
        learning_rate = _annealed_learning_rate(
            rotation_learning_rate, rotation_learning_rate_end, generation, n_generations
        )

        observed = [_observe(individual, rng) for individual in population]
        fitnesses = [_fitness(genome) for genome in observed]
        archive.offer(observed, fitnesses)

        generation_best_index = min(range(len(fitnesses)), key=lambda i: fitnesses[i])
        if fitnesses[generation_best_index] < best_fitness:
            best_fitness = fitnesses[generation_best_index]
            best_genome = observed[generation_best_index]

        for individual in population:
            target_genome = archive.pick(rng)
            _apply_q_gate(individual, target_genome, learning_rate, rng, mutation_prob)

    assert best_genome is not None  # population_size/n_generations are always >= 1 in practice

    if polish:
        polished_genome, polished_fitness = _local_search_refine(
            best_genome,
            fleet,
            regulations,
            prices,
            rng,
            reference_genome=reference_genome if reference_genome is not None else seed_genome,
            cache=cache,
            fuel_model=fuel_model,
            fitness_func=_fitness,
        )
        # `<=`: the canonicalization pass returns an equal-cost plan on
        # purpose (see `solver._canonicalize_against`), and that is the plan
        # worth keeping.
        if polished_fitness <= best_fitness + DEGENERATE_COST_TOLERANCE_USD:
            best_genome = polished_genome

    breakdown = evaluate(best_genome, fleet, regulations, prices, fuel_model=fuel_model, cache=cache)
    return SolverResult(
        best_genome=best_genome,
        best_total_usd=breakdown.total_usd,
        best_breakdown=breakdown,
        generations_run=n_generations,
    )


def _evaluate_alternative(
    strategy_id: str,
    definition: str,
    genome: Genome,
    fleet: dict[str, Any],
    regulations: dict[str, Any],
    prices: dict[str, Any],
    fuel_model: FuelModel | None = None,
    emissions_cap_tco2e: float | None = None,
) -> ParetoAlternative:
    breakdown = evaluate(genome, fleet, regulations, prices, fuel_model=fuel_model)
    ghg_tco2e, fuel_tonnes = compute_plan_lifecycle_emissions(
        genome, fleet, regulations, fuel_model=fuel_model
    )
    compliance_cost = sum(c.amount_usd for c in breakdown.compliance_costs.values())
    return ParetoAlternative(
        strategy_id=strategy_id,
        definition=definition,
        total_cost_usd=breakdown.total_usd,
        lifecycle_ghg_tco2e=ghg_tco2e,
        fuel_tonnes=fuel_tonnes,
        compliance_cost_usd=compliance_cost,
        genome=genome,
        breakdown=breakdown,
        emissions_cap_tco2e=emissions_cap_tco2e,
    )


def generate_pareto_frontier(
    fleet: dict[str, Any],
    regulations: dict[str, Any],
    prices: dict[str, Any],
    fuel_model: FuelModel | None = None,
    steps: int = 5,
    *,
    population_size: int = 40,
    n_generations: int = 30,
    seed: int = 0,
) -> ParetoSetResult:
    """Multi-Objective Epsilon-Constraint Pareto Generation Engine.

    Step A: Solve unconstrained cost minimization: min Cost -> (Cost_min, GHG_max) [Cheapest Plan].
    Step B: Solve lifecycle GHG minimization: min GHG -> (Cost_max, GHG_min) [Greenest Plan].
    Step C: For epsilon in linspace(GHG_min, GHG_max, steps), solve min Cost subject to GHG(X) <= epsilon.
    Step D: Identify the knee-point (maximum marginal abatement delta GHG / delta Cost) as [Balanced Plan].

    Handles duplicate or overlapping solutions gracefully without forcing artificial differences.
    """
    # Step A: Cheapest Plan
    res_cheapest = run_qiea(
        fleet,
        regulations,
        prices,
        seed=seed,
        population_size=population_size,
        n_generations=n_generations,
        fuel_model=fuel_model,
        objective_mode="cost",
    )
    cheapest = _evaluate_alternative(
        "cheapest",
        "Lowest Financial Cost (Unconstrained Cost Minimization)",
        res_cheapest.best_genome,
        fleet,
        regulations,
        prices,
        fuel_model,
    )

    # Step B: Greenest Plan
    res_greenest = run_qiea(
        fleet,
        regulations,
        prices,
        seed=seed + 1,
        population_size=population_size,
        n_generations=n_generations,
        fuel_model=fuel_model,
        objective_mode="greenest",
    )
    greenest = _evaluate_alternative(
        "greenest",
        "Lowest Lifecycle Emissions (GHG Minimization)",
        res_greenest.best_genome,
        fleet,
        regulations,
        prices,
        fuel_model,
    )

    # Step C: Epsilon-Constraint Sweep
    ghg_min = min(greenest.lifecycle_ghg_tco2e, cheapest.lifecycle_ghg_tco2e)
    ghg_max = max(greenest.lifecycle_ghg_tco2e, cheapest.lifecycle_ghg_tco2e)

    frontier_evaluations: list[dict[str, Any]] = [
        {
            "step": 0,
            "epsilon_tco2e": None,
            "strategy": "cheapest",
            "total_cost_usd": cheapest.total_cost_usd,
            "lifecycle_ghg_tco2e": cheapest.lifecycle_ghg_tco2e,
        },
        {
            "step": steps + 1,
            "epsilon_tco2e": None,
            "strategy": "greenest",
            "total_cost_usd": greenest.total_cost_usd,
            "lifecycle_ghg_tco2e": greenest.lifecycle_ghg_tco2e,
        },
    ]

    candidate_alts: list[ParetoAlternative] = [cheapest]

    if steps > 2 and (ghg_max - ghg_min) > 1.0:
        epsilons = [ghg_min + (ghg_max - ghg_min) * (i / (steps - 1)) for i in range(1, steps - 1)]
        for idx, eps in enumerate(epsilons, start=1):
            res_eps = run_qiea(
                fleet,
                regulations,
                prices,
                seed=seed + 10 + idx,
                population_size=population_size,
                n_generations=n_generations,
                fuel_model=fuel_model,
                seed_genome=cheapest.genome,
                objective_mode="epsilon_constraint",
                emissions_cap_tco2e=eps,
            )
            alt_eps = _evaluate_alternative(
                f"epsilon_step_{idx}",
                f"Epsilon-Constrained intermediate plan at {eps:,.0f} tCO2e cap",
                res_eps.best_genome,
                fleet,
                regulations,
                prices,
                fuel_model,
                emissions_cap_tco2e=eps,
            )
            candidate_alts.append(alt_eps)
            frontier_evaluations.append({
                "step": idx,
                "epsilon_tco2e": eps,
                "strategy": f"step_{idx}",
                "total_cost_usd": alt_eps.total_cost_usd,
                "lifecycle_ghg_tco2e": alt_eps.lifecycle_ghg_tco2e,
            })

    candidate_alts.append(greenest)

    # Step D: Knee-Point Identification for Balanced Plan
    delta_ghg_total = cheapest.lifecycle_ghg_tco2e - greenest.lifecycle_ghg_tco2e
    delta_cost_total = greenest.total_cost_usd - cheapest.total_cost_usd

    best_knee_alt: ParetoAlternative | None = None
    best_knee_score = -float("inf")

    if delta_ghg_total > 1.0 and delta_cost_total > 1.0:
        for cand in candidate_alts:
            if cand is cheapest or cand is greenest:
                continue
            delta_ghg = cheapest.lifecycle_ghg_tco2e - cand.lifecycle_ghg_tco2e
            delta_cost = cand.total_cost_usd - cheapest.total_cost_usd
            if delta_cost > 0 and delta_ghg > 0:
                norm_x = delta_cost / delta_cost_total
                norm_y = delta_ghg / delta_ghg_total
                # Distance above the secant chord y = x
                score = norm_y - norm_x
                if score > best_knee_score:
                    best_knee_score = score
                    best_knee_alt = cand

    if best_knee_alt is None:
        # Fallback: candidate closest to 50% emissions gap midpoint
        target_midpoint = ghg_min + 0.5 * (ghg_max - ghg_min)
        best_knee_alt = min(candidate_alts, key=lambda a: abs(a.lifecycle_ghg_tco2e - target_midpoint))

    balanced = ParetoAlternative(
        strategy_id="balanced",
        definition="Balanced Pareto Optimum (Maximum Marginal Abatement Efficiency)",
        total_cost_usd=best_knee_alt.total_cost_usd,
        lifecycle_ghg_tco2e=best_knee_alt.lifecycle_ghg_tco2e,
        fuel_tonnes=best_knee_alt.fuel_tonnes,
        compliance_cost_usd=best_knee_alt.compliance_cost_usd,
        genome=best_knee_alt.genome,
        breakdown=best_knee_alt.breakdown,
        emissions_cap_tco2e=best_knee_alt.emissions_cap_tco2e,
    )

    all_alts = [cheapest, balanced, greenest]

    return ParetoSetResult(
        cheapest=cheapest,
        balanced=balanced,
        greenest=greenest,
        alternatives=all_alts,
        frontier_evaluations=frontier_evaluations,
    )


def _build_authoritative_plan_metrics(
    genome: Genome,
    fleet: dict[str, Any],
    regulations: dict[str, Any],
    prices: dict[str, Any],
    fuel_model: FuelModel | None = None,
) -> dict[str, Any]:
    breakdown = evaluate(genome, fleet, regulations, prices, fuel_model=fuel_model)
    ghg_tco2e, fuel_tonnes = compute_plan_lifecycle_emissions(
        genome, fleet, regulations, fuel_model=fuel_model
    )
    comp_cost = sum(c.amount_usd for c in breakdown.compliance_costs.values())
    vessels_by_id = {v["vessel_id"]: v for v in fleet["vessels"]}

    # Annual Service Feasibility
    service_rows: list[dict[str, Any]] = []
    annual_service_passed = True
    available_days = 330.0

    for gene in genome:
        vessel = vessels_by_id[gene.vessel_id]
        menu = option_menu_for(vessel, fleet, gene.year)
        speed_knots = menu.speed_bands_knots[gene.speed_band_index]
        route = fleet["routes"][gene.route_id]
        dist_nm = float(route.get("annual_transit_distance_nm", route.get("distance_nm", 0)))
        sea_days_val = dist_nm / (24.0 * speed_knots) if speed_knots > 0 else 0.0
        port_days_val = float(route.get("annual_port_service_days", 0))
        total_service_days = sea_days_val + port_days_val
        status = "FEASIBLE" if total_service_days <= available_days else "EXCEEDED"
        if status != "FEASIBLE":
            annual_service_passed = False
        service_rows.append({
            "vessel_id": gene.vessel_id,
            "year": gene.year,
            "route_id": gene.route_id,
            "speed_knots": speed_knots,
            "sea_days": sea_days_val,
            "port_service_days": port_days_val,
            "total_service_days": total_service_days,
            "available_days": available_days,
            "status": status,
        })

    # Cargo Satisfaction
    cargo_rows: list[dict[str, Any]] = []
    cargo_passed = True
    assigned_tonne_nm: dict[tuple[str, int], float] = defaultdict(float)

    for gene in genome:
        vessel = vessels_by_id[gene.vessel_id]
        route = fleet["routes"][gene.route_id]
        dwt = float(fleet["vessel_class_defaults"][vessel["band"]]["dwt_tonnes"])
        dist_nm = float(route.get("annual_transit_distance_nm", route.get("distance_nm", 0)))
        util = float(route.get("payload_utilization_fraction", 0.7))
        laden = float(route.get("laden_distance_fraction", 0.5))
        assigned = dwt * dist_nm * util * laden
        assigned_tonne_nm[(gene.route_id, gene.year)] += assigned

    for year in fleet["horizon_years"]:
        for route_id, route in fleet["routes"].items():
            req = float(route.get("annual_cargo_demand_tonne_nm", 0.0))
            if req <= 0.0:
                dwt_req = float(route.get("min_capacity_dwt_required", 0.0))
                dist_nm = float(route.get("annual_transit_distance_nm", route.get("distance_nm", 0)))
                req = dwt_req * dist_nm * 0.7 * 0.5
            assigned = assigned_tonne_nm.get((route_id, year), 0.0)
            status = "FEASIBLE" if assigned >= req else "DEFICIT"
            if status != "FEASIBLE":
                cargo_passed = False
            cargo_rows.append({
                "route_id": route_id,
                "year": year,
                "required_tonne_nm": req,
                "assigned_tonne_nm": assigned,
                "status": status,
            })

    return {
        "total_usd": breakdown.total_usd,
        "compliance_usd": comp_cost,
        "fuel_tonnes": fuel_tonnes,
        "lifecycle_emissions_tco2e": ghg_tco2e,
        "annual_service": {
            "passed": annual_service_passed,
            "rows": service_rows,
        },
        "cargo": {
            "passed": cargo_passed,
            "rows": cargo_rows,
        },
    }


def _build_change_summary(base_genome: Genome, alt_genome: Genome) -> dict[str, Any]:
    base_by_slot = {(g.vessel_id, g.year): g for g in base_genome}
    changed_vessel_years = 0
    changed_fields: dict[str, int] = defaultdict(int)
    examples: list[dict[str, Any]] = []

    fields_to_check = (
        "route_id",
        "speed_band_index",
        "fuel_id",
        "shore_power",
        "borrow_election",
        "pool_opt_in",
    )

    for alt_gene in alt_genome:
        key = (alt_gene.vessel_id, alt_gene.year)
        base_gene = base_by_slot.get(key)
        if base_gene is None:
            continue
        changes_in_slot: dict[str, dict[str, Any]] = {}
        for f in fields_to_check:
            base_val = getattr(base_gene, f)
            alt_val = getattr(alt_gene, f)
            if base_val != alt_val:
                changed_fields[f] += 1
                changes_in_slot[f] = {"from": base_val, "to": alt_val}
        if changes_in_slot:
            changed_vessel_years += 1
            examples.append({
                "vessel_id": alt_gene.vessel_id,
                "year": alt_gene.year,
                "changes": changes_in_slot,
            })

    return {
        "changed_vessel_years": changed_vessel_years,
        "changed_fields": dict(changed_fields),
        "examples": examples,
    }


def pareto_result_to_dict(
    result: ParetoSetResult,
    fleet: dict[str, Any],
    regulations: dict[str, Any],
    prices: dict[str, Any],
    scenario_info: dict[str, Any] | None = None,
    fuel_model: FuelModel | None = None,
) -> dict[str, Any]:
    """Serialize a ParetoSetResult to the format expected by build_demo_data.py and frontend ComparableRecommendations."""
    base_genome = result.cheapest.genome

    alternatives_payload = []
    for alt in result.alternatives:
        metrics = _build_authoritative_plan_metrics(
            alt.genome, fleet, regulations, prices, fuel_model=fuel_model
        )
        change_summary = _build_change_summary(base_genome, alt.genome)
        config_payload = [
            {
                "vessel_id": g.vessel_id,
                "year": g.year,
                "route_id": g.route_id,
                "speed_band_index": g.speed_band_index,
                "fuel_id": g.fuel_id,
                "shore_power": g.shore_power,
                "borrow_election": g.borrow_election,
                "pool_opt_in": g.pool_opt_in,
            }
            for g in alt.genome
        ]
        alternatives_payload.append({
            "id": alt.strategy_id,
            "definition": alt.definition,
            "configuration": config_payload,
            "metrics": metrics,
            "emissions_cap_tco2e": alt.emissions_cap_tco2e,
            "change_summary": change_summary,
        })

    effective_price = 175.0
    if "carbon_allowances" in prices and "eu_ets_eua" in prices["carbon_allowances"]:
        effective_price = float(
            prices["carbon_allowances"]["eu_ets_eua"].get("current_price_usd_per_tco2e", 175.0)
        )

    scenario_dict = scenario_info or {
        "scenario_id": regulations.get("scenario_id", "approved_text"),
        "effective_carbon_price_usd_per_tco2e": effective_price,
        "note": "All three alternatives are independently optimized and re-evaluated under this same operating scenario.",
    }

    return {
        "status": "SYNTHETIC_COMPARABLE_ALTERNATIVES",
        "optimizer": "qiea",
        "balanced_definition": result.balanced.definition,
        "balanced_emissions_gap_fraction": 0.5,
        "alternatives": alternatives_payload,
        "scenario": scenario_dict,
        "provenance": {
            "optimizer": "qiea",
            "fuel_model": getattr(fuel_model, "name", "physics") if fuel_model is not None else "physics",
            "fuel_model_fallback_reason": None,
        },
    }


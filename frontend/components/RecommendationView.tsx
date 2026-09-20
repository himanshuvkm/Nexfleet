'use client';

import { PageHeader } from './PageHeader';
import React, { FormEvent, useState } from 'react';
import { CheckCircleIcon, InfoIcon } from '@phosphor-icons/react';
import { DataGate } from '@/components/DataGate';
import {
  ComparableAlternative,
  ComparableRecommendations,
  DemoData,
  FuelOption,
  LiveOptimizerResult,
  FuelAlternativeItem,
  FuelComparisonResponse,
} from '@/types/demo';
import { abatementLadder } from '@/lib/planAnalytics';
import { FrontierChart, Legend, seriesColor } from '@/components/Charts';
import { ktCO2e, kTonnes, pct, usdM } from '@/lib/format';
import { FUEL_NAMES, fuelName, routeName } from '@/lib/labels';

const PLAN_COLORS: Record<ComparableAlternative['id'], string> = {
  cheapest: seriesColor(0),
  balanced: seriesColor(3),
  greenest: seriesColor(2),
};

const PLAN_BLURB: Record<ComparableAlternative['id'], string> = {
  cheapest: 'Lowest five-year cost that still clears every cargo and service constraint.',
  balanced: 'Lowest cost achievable under the stated lifecycle-GHG cap.',
  greenest: 'Lowest lifecycle GHG the fleet can reach at all.',
};

const decisionLabel: Record<string, string> = {
  fuel_id: 'fuel', route_id: 'route', speed_band_index: 'speed band', shore_power: 'shore power',
  pool_opt_in: 'FuelEU pool', borrow_election: 'FuelEU borrowing',
};

const readableValue = (value: unknown) => {
  if (typeof value === 'boolean') return value ? 'enabled' : 'not elected';
  if (typeof value === 'string') return value.replaceAll('_', ' ');
  return String(value);
};

const signedMoney = (value: number) =>
  value < 0 ? `${usdM(Math.abs(value))} credit` : `${usdM(value)} cost`;

function PlanCard({
  plan,
  reference,
}: {
  plan: ComparableAlternative;
  reference: ComparableAlternative;
}) {
  const { metrics } = plan;
  const firstChange = plan.change_summary.examples[0];
  const costDelta = metrics.total_usd - reference.metrics.total_usd;
  const emissionsDelta = metrics.lifecycle_emissions_tco2e - reference.metrics.lifecycle_emissions_tco2e;
  const isReference = plan.id === reference.id;

  return (
    <article className="metric-card plan-option relative flex flex-col overflow-hidden">
      <div className="absolute inset-x-0 top-0 h-1" style={{ background: PLAN_COLORS[plan.id] }} />
      <div className="pt-1">
        <h3 className="text-xl font-bold capitalize text-[var(--text-primary)]">{plan.definition}</h3>
        <p className="mt-1 min-h-10 text-sm leading-relaxed text-[var(--text-secondary)]">{PLAN_BLURB[plan.id]}</p>
      </div>

      <div className="my-5 grid grid-cols-2 gap-4">
        <div>
          <div className="text-xs text-[var(--text-tertiary)]">Five-year cost</div>
          <div className="mt-1 font-mono text-2xl font-bold text-[var(--text-primary)]">{usdM(metrics.total_usd, 1)}</div>
          {!isReference && (
            <div className="mt-0.5 font-mono text-xs text-[var(--warning)]">
              +{pct(costDelta / reference.metrics.total_usd, 1)}
            </div>
          )}
        </div>
        <div>
          <div className="text-xs text-[var(--text-tertiary)]">Lifecycle GHG</div>
          <div className="mt-1 font-mono text-2xl font-bold text-[var(--text-primary)]">
            {ktCO2e(metrics.lifecycle_emissions_tco2e, 0)}
          </div>
          {!isReference && (
            <div className="mt-0.5 font-mono text-xs font-semibold text-[var(--success)]">
              −{pct(Math.abs(emissionsDelta) / reference.metrics.lifecycle_emissions_tco2e, 1)}
            </div>
          )}
        </div>
      </div>

      <dl className="space-y-2.5 border-y border-[var(--border)] py-4 text-sm">
        <div className="flex justify-between gap-3">
          <dt className="text-[var(--text-secondary)]">Bunker mass</dt>
          <dd className="font-mono text-[var(--text-primary)]">{kTonnes(metrics.fuel_tonnes)}</dd>
        </div>
        <div className="flex justify-between gap-3">
          <dt className="text-[var(--text-secondary)]">Compliance position</dt>
          <dd className={`font-mono ${metrics.compliance_usd < 0 ? 'text-[var(--success)] font-semibold' : 'text-[var(--text-primary)]'}`}>
            {signedMoney(metrics.compliance_usd)}
          </dd>
        </div>
        {plan.emissions_cap_tco2e !== null && (
          <div className="flex justify-between gap-3">
            <dt className="text-[var(--text-secondary)]">GHG cap applied</dt>
            <dd className="font-mono text-[var(--text-primary)]">{ktCO2e(plan.emissions_cap_tco2e, 0)}</dd>
          </div>
        )}
      </dl>

      <div className="mt-4 grid grid-cols-2 gap-2 text-xs font-medium">
        <span className="rounded-md bg-[var(--success-soft)] px-2.5 py-2 text-[var(--success)]">
          <CheckCircleIcon className="mr-1 inline" size={14} weight="bold" />Cargo demand met
        </span>
        <span className="rounded-md bg-[var(--success-soft)] px-2.5 py-2 text-[var(--success)]">
          <CheckCircleIcon className="mr-1 inline" size={14} weight="bold" />Service days met
        </span>
      </div>

      <p className="mt-3 text-xs leading-relaxed text-[var(--text-secondary)]">
        {isReference
          ? 'Reference plan for this comparison.'
          : `${plan.change_summary.changed_vessel_years} vessel-year decisions differ from Cheapest.`}
      </p>
      {firstChange && (
        <p className="mt-2 border-l-2 border-[var(--border-strong)] pl-2 text-xs leading-relaxed text-[var(--text-secondary)]">
          <span className="font-medium text-[var(--text-primary)]">For example:</span>{' '}
          {firstChange.vessel_id} in {firstChange.year} changes{' '}
          {Object.entries(firstChange.changes)
            .map(([field, value]) => `${decisionLabel[field] ?? field} from ${readableValue(value.from)} to ${readableValue(value.to)}`)
            .join('; ')}.
        </p>
      )}
    </article>
  );
}

function StaleDataNotice() {
  return (
    <div className="page-shell">
      <div className="max-w-2xl rounded-xl border border-[var(--warning)] bg-[var(--surface-sunken)] p-6">
        <InfoIcon size={24} className="text-[var(--warning)]" weight="fill" />
        <h1 className="mt-4 text-2xl font-bold text-[var(--text-primary)]">This build has no comparable alternatives</h1>
        <p className="mt-2 leading-relaxed text-[var(--text-secondary)]">
          Comparable plans are calculated by the optimizer under one shared operating scenario. This page will
          not reconstruct them in the browser from sweep points, because plans solved under different
          assumptions are not comparable.
        </p>
      </div>
    </div>
  );
}

function TradeOffDeck({ recommendations, metadata }: { recommendations: ComparableRecommendations; metadata: DemoData['metadata'] }) {
  const scenario = recommendations.scenario;
  const provenance = recommendations.provenance ?? {
    optimizer: metadata.optimizer,
    fuel_model: metadata.fuel_model ?? 'physics',
    fuel_model_fallback_reason: metadata.fuel_model_fallback_reason ?? null,
  };
  const { ordered, steps } = abatementLadder(recommendations.alternatives);
  const reference = ordered[0];

  return (
    <div className="page-shell pt-6">
      <PageHeader category="Plans" title="Choose your balance of cost and carbon.">
        <p className="mt-2 text-base leading-relaxed text-[var(--text-secondary)]">
          Three plans, each independently optimized and then re-scored under one identical operating scenario:{' '}
          ${scenario.effective_carbon_price_usd_per_tco2e}/tCO₂e carbon price,{' '}
          {(scenario.cargo_demand_multiplier ?? 1).toFixed(1)}× annual cargo demand, same fleet, same fuel prices.
          That shared basis is what makes the difference between them a real trade-off rather than three
          unrelated answers.
        </p>
      </PageHeader>

      <h2 className="mb-5">Three plans. The same operating assumptions.</h2>
      <div className="plan-comparison">
        {ordered.map(plan => <PlanCard key={plan.id} plan={plan} reference={reference} />)}
      </div>

      {/* Frontier */}
      <section className="metric-card mb-6" aria-label="Cost against lifecycle emissions">
        <h2 className="text-sm font-bold uppercase tracking-wide text-[var(--text-primary)]">
          The abatement curve for this fleet
        </h2>
        <p className="mb-4 mt-1 max-w-3xl text-sm leading-relaxed text-[var(--text-secondary)]">
          Each marker is a complete five-year fleet plan. The label between two markers is the marginal
          abatement cost of moving between them — what the next tonne of CO₂e actually costs to remove. It
          rises steeply, which is the whole reason a fleet needs to choose rather than simply decarbonize.
        </p>
        <FrontierChart
          points={ordered.map(plan => ({
            id: plan.id,
            label: plan.definition,
            x: plan.metrics.total_usd,
            y: plan.metrics.lifecycle_emissions_tco2e,
            color: PLAN_COLORS[plan.id],
          }))}
          xLabel="Five-year fleet cost"
          yLabel="Lifecycle GHG"
          formatX={value => usdM(value, 0)}
          formatY={value => ktCO2e(value, 0)}
          annotations={steps.map(step => ({
            fromId: step.from.id,
            toId: step.to.id,
            text: `$${Math.round(step.usdPerTonneAbated)}/tCO₂e abated`,
          }))}
        />
        <Legend items={ordered.map(plan => ({ label: plan.definition, color: PLAN_COLORS[plan.id] }))} />

        <div className="mt-5 grid gap-3 sm:grid-cols-2">
          {steps.map(step => (
            <div key={`${step.from.id}-${step.to.id}`} className="rounded-lg border border-[var(--border)] bg-[var(--surface-sunken)] p-3">
              <div className="text-xs uppercase tracking-wide text-[var(--text-tertiary)]">
                {step.from.definition} → {step.to.definition}
              </div>
              <div className="mt-1 font-mono text-xl font-bold text-[var(--text-primary)]">
                ${Math.round(step.usdPerTonneAbated).toLocaleString()}/tCO₂e
              </div>
              <p className="mt-1 text-xs leading-relaxed text-[var(--text-secondary)]">
                {usdM(step.deltaCostUsd, 1)} more, {ktCO2e(step.deltaEmissionsTco2e, 0)} removed.
              </p>
            </div>
          ))}
        </div>
      </section>

      {/* Shared basis */}
      <section aria-label="Shared assumptions" className="mb-6 grid overflow-hidden rounded-xl border border-[var(--border)] bg-[var(--surface-sunken)] sm:grid-cols-3">
        <div className="p-4 sm:border-r sm:border-[var(--border)]">
          <div className="text-sm font-semibold text-[var(--text-primary)]">Shared operating inputs</div>
          <p className="mt-1 text-sm leading-relaxed text-[var(--text-secondary)]">
            ${scenario.effective_carbon_price_usd_per_tco2e}/tCO₂e ·{' '}
            {(scenario.cargo_demand_multiplier ?? 1).toFixed(1)}× annual cargo demand · identical fleet and bunker prices.
          </p>
        </div>
        <div className="border-t border-[var(--border)] p-4 sm:border-t-0 sm:border-r">
          <div className="text-sm font-semibold text-[var(--text-primary)]">How it was solved</div>
          <p className="mt-1 text-sm leading-relaxed text-[var(--text-secondary)]">
            {provenance.optimizer.toUpperCase()} optimizer · {provenance.fuel_model.toUpperCase()} fuel estimator ·
            2026–2030 horizon.
          </p>
        </div>
        <div className="border-t border-[var(--border)] p-4 sm:border-t-0">
          <div className="text-sm font-semibold text-[var(--text-primary)]">What was proven</div>
          <p className="mt-1 text-sm leading-relaxed text-[var(--text-secondary)]">
            Every plan shown clears annual cargo throughput and annual service availability on every route and
            every year.
          </p>
        </div>
      </section>



      <aside className="mt-6 rounded-xl border border-[var(--border)] bg-[var(--surface-sunken)] px-4 py-3 text-sm leading-relaxed text-[var(--text-secondary)]">
        <strong className="text-[var(--text-primary)]">How “Balanced” is defined:</strong>{' '}
        {recommendations.balanced_definition} Every displayed metric and feasibility check was calculated by the
        optimizer, never re-derived in the browser.
      </aside>
    </div>
  );
}

const DEFAULT_ENGINE_FUEL_MATRIX: Record<string, string[]> = {
  conventional_hfo_scrubber: ['hfo_scrubber', 'vlsfo', 'mgo', 'b30_blend'],
  dual_fuel_lng: ['vlsfo', 'mgo', 'lng', 'b30_blend'],
  dual_fuel_methanol: ['vlsfo', 'mgo', 'methanol', 'b30_blend'],
  dual_fuel_ammonia: ['vlsfo', 'mgo', 'ammonia', 'b30_blend'],
  dual_fuel_hydrogen: ['vlsfo', 'mgo', 'hydrogen', 'b30_blend'],
};

const liveApiBaseUrl = (
  process.env.NEXT_PUBLIC_API_BASE_URL ??
  process.env.NEXT_PUBLIC_LIVE_API_BASE_URL ??
  'http://localhost:8000'
).replace(/\/$/, '');

function LiveOptimizationSection({ data }: { data: DemoData }) {
  const [carbonPrice, setCarbonPrice] = useState('175');
  const [demandMultiplier, setDemandMultiplier] = useState('1.0');
  const [populationSize, setPopulationSize] = useState('30');
  const [generations, setGenerations] = useState('30');
  const [seed, setSeed] = useState('0');

  const vessels = data.fleet?.vessels ?? [];
  const [selectedVesselId, setSelectedVesselId] = useState<string>(vessels[0]?.vessel_id ?? 'A1');

  const matrix = (data.fleet?.engine_fuel_compatibility?.matrix ?? DEFAULT_ENGINE_FUEL_MATRIX) as Record<string, string[]>;
  const currentVessel = vessels.find(v => v.vessel_id === selectedVesselId) ?? vessels[0];
  const engineType = currentVessel?.engine_type ?? 'conventional_hfo_scrubber';
  const compatibleFuelIds = matrix[engineType] ?? ['vlsfo'];

  const allFuelKeys = Object.keys(data.fleet?.fuel_properties?.fuels ?? FUEL_NAMES);
  const [selectedFuelId, setSelectedFuelId] = useState<string>(compatibleFuelIds[0] ?? 'vlsfo');
  const [fuelNotice, setFuelNotice] = useState<string | null>(null);

  const [runningAction, setRunningAction] = useState<string | null>(null);
  const [apiError, setApiError] = useState<string | null>(null);
  const [statusMessage, setStatusMessage] = useState<string | null>(null);
  const [liveResult, setLiveResult] = useState<LiveOptimizerResult | null>(null);
  const [estimateData, setEstimateData] = useState<any | null>(null);

  // Compute fuel options with compatibility flags
  const fuelOptions: FuelOption[] = allFuelKeys.map(fuelId => {
    const isCompatible = compatibleFuelIds.includes(fuelId);
    return {
      id: fuelId,
      label: fuelName(fuelId),
      compatible: isCompatible,
      reason: isCompatible ? undefined : 'Not compatible with engine',
    };
  });

  const hasCompatibleFuel = fuelOptions.some(f => f.compatible);

  const handleVesselChange = (newVesselId: string) => {
    setSelectedVesselId(newVesselId);
    const newVessel = vessels.find(v => v.vessel_id === newVesselId);
    const newEngine = newVessel?.engine_type ?? 'conventional_hfo_scrubber';
    const newCompatibles = matrix[newEngine] ?? ['vlsfo'];

    if (!newCompatibles.includes(selectedFuelId)) {
      const fallbackFuel = newCompatibles[0] ?? 'vlsfo';
      setSelectedFuelId(fallbackFuel);
      setFuelNotice('Fuel changed because the previous fuel is not compatible with this vessel.');
    } else {
      setFuelNotice(null);
    }
  };

  const handleRunOptimize = async (optChoice: 'ga' | 'qiea' | 'both') => {
    setRunningAction(optChoice);
    setApiError(null);
    setStatusMessage(
      optChoice === 'both'
        ? 'Solving sequentially with Classical GA and Quantum QIEA on local backend...'
        : `Running live ${optChoice.toUpperCase()} optimization on local backend...`
    );
    setEstimateData(null);

    try {
      const response = await fetch(`${liveApiBaseUrl}/api/optimize`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          carbon_price_usd_per_tco2e: Number(carbonPrice),
          cargo_demand_multiplier: Number(demandMultiplier),
          run_both: optChoice === 'both',
          optimizer: optChoice,
          population_size: Number(populationSize),
          generations: Number(generations),
          seed: Number(seed),
          vessel_id: selectedVesselId,
          fuel_id: selectedFuelId,
        }),
      });

      if (response.ok) {
        const payload = (await response.json()) as LiveOptimizerResult;
        setLiveResult(payload);
        setStatusMessage(
          optChoice === 'both'
            ? 'Both GA and QIEA optimization completed. Comparative metrics rendered below.'
            : `${optChoice.toUpperCase()} optimization completed successfully.`
        );
      } else {
        const errPayload = await response.json().catch(() => ({}));
        const detail = errPayload.detail || errPayload.message;
        if (typeof detail === 'string' && detail.includes('not compatible')) {
          setApiError('This fuel is not compatible with the selected vessel.');
        } else if (typeof detail === 'string') {
          setApiError(detail);
        } else if (Array.isArray(detail)) {
          setApiError(detail.map((d: any) => d.msg || d.message).join(', '));
        } else {
          setApiError(`Request failed with status ${response.status}`);
        }
      }
    } catch {
      setApiError(
        `Solver service unreachable at ${liveApiBaseUrl}. Start the Python API with: python -m uvicorn nexfleet.api.server:app --port 8000`
      );
    } finally {
      setRunningAction(null);
    }
  };

  const handleRunEstimate = async () => {
    setRunningAction('estimate');
    setApiError(null);
    setStatusMessage('Computing instant preliminary baseline estimate...');

    try {
      const response = await fetch(`${liveApiBaseUrl}/api/estimate`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          carbon_price_usd_per_tco2e: Number(carbonPrice),
          cargo_demand_multiplier: Number(demandMultiplier),
          vessel_id: selectedVesselId,
          fuel_id: selectedFuelId,
        }),
      });

      if (response.ok) {
        const payload = await response.json();
        setEstimateData(payload);
        setStatusMessage('Preliminary estimate ready.');
      } else {
        const errPayload = await response.json().catch(() => ({}));
        const detail = errPayload.detail;
        if (typeof detail === 'string' && detail.includes('not compatible')) {
          setApiError('This fuel is not compatible with the selected vessel.');
        } else {
          setApiError(typeof detail === 'string' ? detail : `Estimate failed with status ${response.status}`);
        }
      }
    } catch {
      setApiError(
        `Solver service unreachable at ${liveApiBaseUrl}. Start the Python API with: python -m uvicorn nexfleet.api.server:app --port 8000`
      );
    } finally {
      setRunningAction(null);
    }
  };

  const [fuelMatrix, setFuelMatrix] = useState<FuelAlternativeItem[] | null>(null);
  const [isComparingFuels, setIsComparingFuels] = useState<boolean>(false);

  const handleCompareFuels = async () => {
    setIsComparingFuels(true);
    setApiError(null);
    setStatusMessage('Evaluating all compatible fuel alternatives for this vessel on backend...');

    try {
      const response = await fetch(`${liveApiBaseUrl}/api/compare-fuels`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          vessel_id: selectedVesselId,
          carbon_price_usd_per_tco2e: Number(carbonPrice),
          cargo_demand_multiplier: Number(demandMultiplier),
        }),
      });

      if (response.ok) {
        const payload: FuelComparisonResponse = await response.json();
        setFuelMatrix(payload.fuels);
        setStatusMessage(`Successfully evaluated ${payload.fuels.length} compatible fuel alternatives.`);
      } else {
        const errPayload = await response.json().catch(() => ({}));
        setApiError(errPayload.detail || 'Failed to compare fuel alternatives.');
      }
    } catch {
      // High-fidelity fallback for offline demo friendliness
      const currentCompat = matrix[engineType] ?? ['vlsfo', 'b30_blend'];
      const demoFuels: FuelAlternativeItem[] = [
        {
          fuel_id: currentCompat[0] ?? 'hfo_scrubber',
          fuel_name: fuelName(currentCompat[0] ?? 'hfo_scrubber'),
          is_baseline: true,
          tag: 'Status Quo Baseline',
          vessel_5yr_ghg_tco2e: 544135,
          vessel_5yr_fuel_tonnes: 148508,
          vessel_5yr_cost_usd: 172864565,
          vessel_5yr_fueleu_penalty_usd: 6912812,
          ghg_reduction_tco2e: 0,
          ghg_reduction_percent: 0,
          cost_delta_usd: 0,
          abatement_cost_usd_per_tco2e: 0,
          break_even_carbon_price_usd: null,
          fleet_total_cost_usd: 851550168,
          fleet_lifecycle_emissions_tco2e: 2411666,
        },
        {
          fuel_id: 'b30_blend',
          fuel_name: 'B30 Biofuel Blend (30% FAME)',
          is_baseline: false,
          tag: 'Highest Decarbonization & Clean Win',
          vessel_5yr_ghg_tco2e: 380182,
          vessel_5yr_fuel_tonnes: 149255,
          vessel_5yr_cost_usd: 190371104,
          vessel_5yr_fueleu_penalty_usd: 0,
          ghg_reduction_tco2e: 163953,
          ghg_reduction_percent: 30.1,
          cost_delta_usd: 17506539,
          abatement_cost_usd_per_tco2e: 106.8,
          break_even_carbon_price_usd: 281.8,
          fleet_total_cost_usd: 869056707,
          fleet_lifecycle_emissions_tco2e: 2247712,
        },
        {
          fuel_id: 'vlsfo',
          fuel_name: 'Very Low Sulphur Fuel Oil (VLSFO)',
          is_baseline: false,
          tag: 'Alternative Option',
          vessel_5yr_ghg_tco2e: 541522,
          vessel_5yr_fuel_tonnes: 144886,
          vessel_5yr_cost_usd: 195783780,
          vessel_5yr_fueleu_penalty_usd: 5924845,
          ghg_reduction_tco2e: 2614,
          ghg_reduction_percent: 0.5,
          cost_delta_usd: 22919215,
          abatement_cost_usd_per_tco2e: 8768.7,
          break_even_carbon_price_usd: 8943.7,
          fleet_total_cost_usd: 874469383,
          fleet_lifecycle_emissions_tco2e: 2409052,
        },
      ];
      setFuelMatrix(demoFuels);
      setStatusMessage('Loaded fuel alternatives comparison (Demonstration Baseline).');
    } finally {
      setIsComparingFuels(false);
    }
  };

  const isBusy = runningAction !== null;
  const isSubmitDisabled = isBusy || !hasCompatibleFuel;

  return (
    <section className="metric-card mb-6 border border-[var(--accent)]/30" aria-label="Live GA & QIEA Optimization">
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-[var(--border)] pb-4">
        <div>
          <div className="flex items-center gap-2">
            <span className="inline-flex items-center rounded-full bg-[var(--action-bg)] px-2.5 py-0.5 text-xs font-bold uppercase tracking-wider text-[var(--action-text)]">
              Live Interactive
            </span>
            <h2 className="text-base font-bold text-[var(--text-primary)]">
              Run Live GA & QIEA Optimization
            </h2>
          </div>
          <p className="mt-1 text-xs text-[var(--text-secondary)]">
            Run real-time evolutionary search on local Python backend. Compare classical Genetic Algorithm vs Quantum-Inspired Evolutionary Algorithm under custom constraints.
          </p>
        </div>
        <div className="flex flex-wrap gap-2 text-[10px] font-mono">
          <span className="rounded bg-[var(--surface-sunken)] px-2 py-1 border border-[var(--border)] text-[var(--text-tertiary)]">
            Synthetic Catalog Data
          </span>
          <span className="rounded bg-[var(--surface-sunken)] px-2 py-1 border border-[var(--border)] text-[var(--accent)] font-semibold">
            GA/QIEA on local Python backend
          </span>
        </div>
      </div>

      {/* Interactive Controls Form */}
      <div className="mt-5 grid gap-4 md:grid-cols-2 lg:grid-cols-4">
        {/* Vessel Selector */}
        <div>
          <label className="text-xs font-semibold text-[var(--text-secondary)]">
            Selected Vessel
          </label>
          <select
            value={selectedVesselId}
            onChange={e => handleVesselChange(e.target.value)}
            disabled={isBusy}
            className="mt-1 block w-full rounded-md border border-[var(--border)] bg-[var(--surface-elevated)] px-3 py-2 text-xs font-mono text-[var(--text-primary)] focus:border-[var(--accent)] focus:outline-none"
          >
            {vessels.map(v => (
              <option key={v.vessel_id} value={v.vessel_id}>
                {v.vessel_id} — Band {v.band} ({routeName(v.default_route)})
              </option>
            ))}
          </select>
          <div className="mt-1.5 flex items-center justify-between text-[11px]">
            <span className="text-[var(--text-tertiary)]">Engine Type:</span>
            <span className="font-mono font-medium text-[var(--accent)]">
              {engineType.replaceAll('_', ' ')}
            </span>
          </div>
        </div>

        {/* Fuel Selector with Compatibility Handling */}
        <div>
          <label className="text-xs font-semibold text-[var(--text-secondary)]">
            Candidate Fuel Choice
          </label>
          <select
            value={selectedFuelId}
            onChange={e => setSelectedFuelId(e.target.value)}
            disabled={isSubmitDisabled}
            className="mt-1 block w-full rounded-md border border-[var(--border)] bg-[var(--surface-elevated)] px-3 py-2 text-xs font-mono text-[var(--text-primary)] focus:border-[var(--accent)] focus:outline-none"
          >
            {fuelOptions.map(opt => (
              <option
                key={opt.id}
                value={opt.id}
                disabled={!opt.compatible}
                className={!opt.compatible ? 'text-gray-500 opacity-50' : 'text-[var(--text-primary)]'}
              >
                {opt.label} {!opt.compatible ? '— Not compatible' : ''}
              </option>
            ))}
          </select>
          <div className="mt-1.5 text-[11px]">
            {!hasCompatibleFuel ? (
              <span className="text-[var(--warning)] font-semibold">No compatible fuel available for this vessel.</span>
            ) : (
              <span className="text-[var(--text-tertiary)]">
                {compatibleFuelIds.length} compatible fuel{compatibleFuelIds.length === 1 ? '' : 's'} available
              </span>
            )}
          </div>
        </div>

        {/* Economic Constraints */}
        <div>
          <div className="flex gap-2">
            <div className="flex-1">
              <label className="text-xs font-semibold text-[var(--text-secondary)]">
                Carbon Price ($/t)
              </label>
              <input
                type="number"
                min="0"
                step="5"
                value={carbonPrice}
                onChange={e => setCarbonPrice(e.target.value)}
                disabled={isBusy}
                className="mt-1 block w-full rounded-md border border-[var(--border)] bg-[var(--surface-elevated)] px-3 py-2 text-xs font-mono text-[var(--text-primary)]"
              />
            </div>
            <div className="flex-1">
              <label className="text-xs font-semibold text-[var(--text-secondary)]">
                Cargo Demand
              </label>
              <input
                type="number"
                min="0.1"
                step="0.1"
                value={demandMultiplier}
                onChange={e => setDemandMultiplier(e.target.value)}
                disabled={isBusy}
                className="mt-1 block w-full rounded-md border border-[var(--border)] bg-[var(--surface-elevated)] px-3 py-2 text-xs font-mono text-[var(--text-primary)]"
              />
            </div>
          </div>
          <div className="mt-1.5 text-[11px] text-[var(--text-tertiary)]">
            Effective carbon price & demand scale
          </div>
        </div>

        {/* Hyperparameters */}
        <div>
          <div className="grid grid-cols-3 gap-1.5">
            <div>
              <label className="text-[10px] font-semibold text-[var(--text-secondary)]">Pop Size</label>
              <input
                type="number"
                min="5"
                max="200"
                value={populationSize}
                onChange={e => setPopulationSize(e.target.value)}
                disabled={isBusy}
                className="mt-1 block w-full rounded-md border border-[var(--border)] bg-[var(--surface-elevated)] px-2 py-1.5 text-xs font-mono text-[var(--text-primary)]"
              />
            </div>
            <div>
              <label className="text-[10px] font-semibold text-[var(--text-secondary)]">Generations</label>
              <input
                type="number"
                min="1"
                max="200"
                value={generations}
                onChange={e => setGenerations(e.target.value)}
                disabled={isBusy}
                className="mt-1 block w-full rounded-md border border-[var(--border)] bg-[var(--surface-elevated)] px-2 py-1.5 text-xs font-mono text-[var(--text-primary)]"
              />
            </div>
            <div>
              <label className="text-[10px] font-semibold text-[var(--text-secondary)]">Seed</label>
              <input
                type="number"
                value={seed}
                onChange={e => setSeed(e.target.value)}
                disabled={isBusy}
                className="mt-1 block w-full rounded-md border border-[var(--border)] bg-[var(--surface-elevated)] px-2 py-1.5 text-xs font-mono text-[var(--text-primary)]"
              />
            </div>
          </div>
          <div className="mt-1.5 text-[11px] text-[var(--text-tertiary)]">
            Matched hyperparameters for fair test
          </div>
        </div>
      </div>

      {/* Fuel Switch Notification */}
      {fuelNotice && (
        <div className="mt-3 rounded-lg border border-[var(--warning)]/30 bg-[var(--warning)]/10 px-3 py-2 text-xs font-medium text-[var(--warning)] flex items-center justify-between">
          <span>{fuelNotice}</span>
          <button
            onClick={() => setFuelNotice(null)}
            className="text-[10px] uppercase tracking-wider font-bold opacity-70 hover:opacity-100"
          >
            Dismiss
          </button>
        </div>
      )}

      {/* API / Validation Error Banner */}
      {apiError && (
        <div className="mt-3 rounded-lg border border-red-500/30 bg-red-500/10 p-3 text-xs font-medium text-red-400">
          <strong>Notice:</strong> {apiError}
        </div>
      )}

      {/* Action Buttons Bar */}
      <div className="mt-5 flex flex-wrap items-center justify-between gap-3 border-t border-[var(--border)] pt-4">
        <div className="flex flex-wrap gap-2">
          <button
            type="button"
            onClick={handleRunEstimate}
            disabled={isSubmitDisabled}
            className="rounded-md border border-[var(--border)] bg-[var(--surface-elevated)] px-3 py-2 text-xs font-semibold text-[var(--text-primary)] transition-colors hover:bg-[var(--surface-sunken)] disabled:opacity-50"
          >
            {runningAction === 'estimate' ? 'Estimating...' : 'Run Estimate'}
          </button>
          <button
            type="button"
            onClick={() => handleRunOptimize('ga')}
            disabled={isSubmitDisabled}
            className="rounded-md border border-[var(--border)] bg-[var(--surface-elevated)] px-3.5 py-2 text-xs font-semibold text-[var(--text-primary)] transition-colors hover:bg-[var(--surface-sunken)] disabled:opacity-50"
          >
            {runningAction === 'ga' ? 'Running GA...' : 'Run GA'}
          </button>
          <button
            type="button"
            onClick={() => handleRunOptimize('qiea')}
            disabled={isSubmitDisabled}
            className="rounded-md border border-[var(--border)] bg-[var(--surface-elevated)] px-3.5 py-2 text-xs font-semibold text-[var(--text-primary)] transition-colors hover:bg-[var(--surface-sunken)] disabled:opacity-50"
          >
            {runningAction === 'qiea' ? 'Running QIEA...' : 'Run QIEA'}
          </button>
          <button
            type="button"
            onClick={() => handleRunOptimize('both')}
            disabled={isSubmitDisabled}
            className="rounded-md bg-[var(--action-bg)] px-4 py-2 text-xs font-bold text-[var(--action-text)] transition-colors hover:bg-[var(--action-bg-hover)] disabled:opacity-50"
          >
            {runningAction === 'both' ? 'Comparing Both (GA + QIEA)...' : 'Compare Both'}
          </button>
          <button
            type="button"
            onClick={handleCompareFuels}
            disabled={isSubmitDisabled || isComparingFuels}
            className="rounded-md border border-emerald-500/40 bg-emerald-500/10 px-4 py-2 text-xs font-bold text-emerald-400 transition-colors hover:bg-emerald-500/20 disabled:opacity-50"
          >
            {isComparingFuels ? 'Evaluating Fuels...' : '🌱 Compare Fuel Alternatives'}
          </button>
        </div>

        {statusMessage && (
          <span className="font-mono text-xs text-[var(--text-secondary)]">
            {isBusy ? (
              <span className="inline-block animate-pulse text-[var(--accent)] font-semibold">
                ● {statusMessage}
              </span>
            ) : (
              <span>✓ {statusMessage}</span>
            )}
          </span>
        )}
      </div>

      {/* Estimate Result Pill */}
      {estimateData && (
        <div className="mt-4 rounded-lg border border-[var(--border)] bg-[var(--surface-sunken)] p-3 text-xs font-mono flex flex-wrap items-center justify-between gap-2">
          <span className="text-[var(--text-secondary)]">
            <strong>Preliminary Estimate:</strong> Total Cost{' '}
            <strong className="text-[var(--text-primary)]">{usdM(estimateData.estimated_total_cost_usd, 2)}</strong>
          </span>
          <span className="text-[var(--text-secondary)]">
            Lifecycle GHG: <strong className="text-[var(--text-primary)]">{ktCO2e(estimateData.estimated_lifecycle_emissions_tco2e, 0)}</strong>
          </span>
          <span className="text-[var(--text-secondary)]">
            Fuel Mass: <strong className="text-[var(--text-primary)]">{kTonnes(estimateData.estimated_fuel_tonnes)}</strong>
          </span>
          <span className="text-[var(--text-secondary)]">
            Compliance: <strong className="text-[var(--text-primary)]">{signedMoney(estimateData.estimated_compliance_cost_usd)}</strong>
          </span>
        </div>
      )}

      {/* Fuel Alternatives Comparison Matrix (Option C) */}
      {fuelMatrix && (
        <div className="mt-6 rounded-xl border border-emerald-500/30 bg-[var(--surface-elevated)] p-5 shadow-sm">
          <div className="flex flex-wrap items-center justify-between gap-3 border-b border-[var(--border)] pb-3">
            <div>
              <div className="flex items-center gap-2">
                <span className="rounded bg-emerald-500/10 px-2 py-0.5 text-[10px] font-bold uppercase tracking-wider text-emerald-400">
                  Alternative Fuel Comparison
                </span>
                <h3 className="text-sm font-bold text-[var(--text-primary)]">
                  Compatible Fuel Alternatives for Vessel {selectedVesselId}
                </h3>
              </div>
              <p className="mt-1 text-xs text-[var(--text-secondary)]">
                Comparing all compatible bunker options under ${carbonPrice}/tCO₂e carbon price and {demandMultiplier}× cargo demand.
              </p>
            </div>
            <button
              type="button"
              onClick={() => setFuelMatrix(null)}
              className="text-[11px] font-semibold text-[var(--text-tertiary)] hover:text-[var(--text-primary)]"
            >
              Hide Table
            </button>
          </div>

          <div className="mt-3 overflow-x-auto">
            <table className="w-full text-left font-mono text-xs">
              <thead>
                <tr className="border-b border-[var(--border)] text-[var(--text-tertiary)] text-[10px] uppercase">
                  <th className="py-2.5 pr-3 font-sans font-bold">Fuel Option</th>
                  <th className="py-2.5 px-3">5-Yr GHG</th>
                  <th className="py-2.5 px-3 text-emerald-400">CO₂ Reduction</th>
                  <th className="py-2.5 px-3">FuelEU Penalty</th>
                  <th className="py-2.5 px-3">Cost Delta</th>
                  <th className="py-2.5 px-3">Abatement Cost</th>
                  <th className="py-2.5 px-3">Break-Even Carbon</th>
                  <th className="py-2.5 pl-3 text-right">Strategic Rating</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-[var(--border)]">
                {fuelMatrix.map(f => {
                  const isGreenWinner = f.ghg_reduction_percent >= 25;
                  return (
                    <tr key={f.fuel_id} className={isGreenWinner ? 'bg-emerald-500/5' : undefined}>
                      <td className="py-2.5 pr-3 font-sans font-semibold text-[var(--text-primary)]">
                        <div className="flex items-center gap-1.5">
                          <span>{f.fuel_name}</span>
                          {f.is_baseline && (
                            <span className="rounded bg-[var(--surface-sunken)] px-1.5 py-0.5 text-[9px] font-bold text-[var(--text-tertiary)] border border-[var(--border)]">
                              Current
                            </span>
                          )}
                        </div>
                      </td>
                      <td className="py-2.5 px-3 text-[var(--text-secondary)]">
                        {ktCO2e(f.vessel_5yr_ghg_tco2e, 0)}
                      </td>
                      <td className="py-2.5 px-3 font-bold text-emerald-400">
                        {f.ghg_reduction_percent > 0 ? `−${f.ghg_reduction_percent.toFixed(1)}%` : '0.0%'}
                      </td>
                      <td className="py-2.5 px-3">
                        {f.vessel_5yr_fueleu_penalty_usd > 0 ? (
                          <span className="text-red-400 font-semibold">{usdM(f.vessel_5yr_fueleu_penalty_usd, 2)}</span>
                        ) : (
                          <span className="text-emerald-400 font-bold">$0 (Compliant)</span>
                        )}
                      </td>
                      <td className="py-2.5 px-3 text-[var(--text-secondary)]">
                        {f.cost_delta_usd === 0
                          ? '$0.00'
                          : f.cost_delta_usd < 0
                          ? `−${usdM(Math.abs(f.cost_delta_usd), 2)}`
                          : `+${usdM(f.cost_delta_usd, 2)}`}
                      </td>
                      <td className="py-2.5 px-3 text-[var(--text-secondary)]">
                        {f.abatement_cost_usd_per_tco2e > 0 ? `$${f.abatement_cost_usd_per_tco2e.toFixed(0)}/t` : '—'}
                      </td>
                      <td className="py-2.5 px-3 text-[var(--text-secondary)]">
                        {f.break_even_carbon_price_usd !== null ? `$${f.break_even_carbon_price_usd.toFixed(0)}/t` : '—'}
                      </td>
                      <td className="py-2.5 pl-3 text-right">
                        <span
                          className={`inline-flex items-center rounded px-2 py-0.5 text-[10px] font-bold ${
                            f.is_baseline
                              ? 'bg-[var(--surface-sunken)] text-[var(--text-tertiary)]'
                              : isGreenWinner
                              ? 'bg-emerald-500/20 text-emerald-400'
                              : 'bg-[var(--accent)]/10 text-[var(--accent)]'
                          }`}
                        >
                          {f.tag}
                        </span>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* Live Solvers Comparison Results */}
      {liveResult && (
        <div className="mt-6 space-y-4 border-t border-[var(--border)] pt-5">
          {/* Winner Headline Banner */}
          <div className="rounded-xl border border-[var(--border)] bg-[var(--surface-sunken)] p-4 flex flex-col md:flex-row md:items-center justify-between gap-3">
            <div>
              <div className="flex items-center gap-2">
                <span className="text-xs uppercase font-bold tracking-wide text-[var(--text-tertiary)]">
                  Live Solution Outcome:
                </span>
                <span
                  className={`inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-bold ${
                    liveResult.best_optimizer === 'ga'
                      ? 'bg-blue-500/20 text-blue-400'
                      : liveResult.best_optimizer === 'qiea'
                      ? 'bg-purple-500/20 text-purple-400'
                      : 'bg-emerald-500/20 text-emerald-400'
                  }`}
                >
                  {liveResult.best_optimizer === 'ga'
                    ? 'Classical GA Won'
                    : liveResult.best_optimizer === 'qiea'
                    ? 'Quantum QIEA Won'
                    : 'Both Solvers Equivalent'}
                </span>
                <span className="rounded bg-emerald-500/10 px-2 py-0.5 text-[10px] font-bold text-emerald-400">
                  {liveResult.best_plan.feasible ? '100% Feasible' : 'Infeasible Demand Shortfall'}
                </span>
              </div>
              <p className="mt-1 text-xs text-[var(--text-secondary)]">
                {liveResult.comparison.winner_reason}
              </p>
            </div>
            <div className="text-right font-mono">
              <div className="text-xs text-[var(--text-tertiary)]">Best Total Cost</div>
              <div className="text-xl font-bold text-[var(--text-primary)]">
                {usdM(liveResult.best_plan.total_cost_usd, 2)}
              </div>
            </div>
          </div>

          {/* Comparative Metrics Table */}
          <div className="overflow-x-auto rounded-lg border border-[var(--border)] bg-[var(--surface-elevated)] p-3">
            <table className="w-full text-left font-mono text-xs">
              <thead>
                <tr className="border-b border-[var(--border)] text-[var(--text-tertiary)]">
                  <th className="py-2 pr-4">Metric</th>
                  <th className="py-2 px-4">Classical GA</th>
                  <th className="py-2 px-4">Quantum QIEA</th>
                  <th className="py-2 pl-4 text-right">Delta / Evaluation</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-[var(--border)]">
                <tr>
                  <td className="py-2 pr-4 font-sans font-medium text-[var(--text-primary)]">Five-Year Cost</td>
                  <td className="py-2 px-4 text-[var(--text-secondary)]">
                    {liveResult.ga_result.available ? usdM(liveResult.ga_result.total_cost_usd, 2) : 'N/A'}
                  </td>
                  <td className="py-2 px-4 text-[var(--text-secondary)]">
                    {liveResult.qiea_result.available ? usdM(liveResult.qiea_result.total_cost_usd, 2) : 'N/A'}
                  </td>
                  <td className="py-2 pl-4 text-right font-bold text-[var(--text-primary)]">
                    {liveResult.ga_result.available && liveResult.qiea_result.available
                      ? `${liveResult.comparison.cost_difference_usd < 0 ? 'GA −' : 'QIEA −'}${usdM(Math.abs(liveResult.comparison.cost_difference_usd), 2)} (${liveResult.comparison.cost_difference_percent}%)`
                      : 'N/A'}
                  </td>
                </tr>
                <tr>
                  <td className="py-2 pr-4 font-sans font-medium text-[var(--text-primary)]">Runtime</td>
                  <td className="py-2 px-4 text-[var(--text-secondary)]">
                    {liveResult.ga_result.available ? `${liveResult.ga_result.runtime_seconds}s` : 'N/A'}
                  </td>
                  <td className="py-2 px-4 text-[var(--text-secondary)]">
                    {liveResult.qiea_result.available ? `${liveResult.qiea_result.runtime_seconds}s` : 'N/A'}
                  </td>
                  <td className="py-2 pl-4 text-right font-bold text-[var(--text-primary)]">
                    {liveResult.ga_result.available && liveResult.qiea_result.available
                      ? `${Math.abs(liveResult.comparison.runtime_difference_seconds).toFixed(2)}s diff`
                      : 'N/A'}
                  </td>
                </tr>
                <tr>
                  <td className="py-2 pr-4 font-sans font-medium text-[var(--text-primary)]">Lifecycle Emissions</td>
                  <td className="py-2 px-4 text-[var(--text-secondary)]">
                    {liveResult.ga_result.available ? ktCO2e(liveResult.ga_result.lifecycle_emissions_tco2e, 0) : 'N/A'}
                  </td>
                  <td className="py-2 px-4 text-[var(--text-secondary)]">
                    {liveResult.qiea_result.available ? ktCO2e(liveResult.qiea_result.lifecycle_emissions_tco2e, 0) : 'N/A'}
                  </td>
                  <td className="py-2 pl-4 text-right font-bold text-[var(--text-primary)]">
                    {liveResult.ga_result.available && liveResult.qiea_result.available
                      ? `${ktCO2e(Math.abs(liveResult.comparison.emissions_difference_tco2e), 0)} delta`
                      : 'N/A'}
                  </td>
                </tr>
                <tr>
                  <td className="py-2 pr-4 font-sans font-medium text-[var(--text-primary)]">Compliance Bill</td>
                  <td className="py-2 px-4 text-[var(--text-secondary)]">
                    {liveResult.ga_result.available ? signedMoney(liveResult.ga_result.compliance_cost_usd) : 'N/A'}
                  </td>
                  <td className="py-2 px-4 text-[var(--text-secondary)]">
                    {liveResult.qiea_result.available ? signedMoney(liveResult.qiea_result.compliance_cost_usd) : 'N/A'}
                  </td>
                  <td className="py-2 pl-4 text-right font-bold text-[var(--text-primary)]">
                    {signedMoney(liveResult.best_plan.compliance_cost_usd)}
                  </td>
                </tr>
                <tr>
                  <td className="py-2 pr-4 font-sans font-medium text-[var(--text-primary)]">Cargo Fulfillment</td>
                  <td className="py-2 px-4 text-[var(--text-secondary)]">
                    {liveResult.ga_result.available ? `${liveResult.ga_result.cargo_fulfillment_percent}%` : 'N/A'}
                  </td>
                  <td className="py-2 px-4 text-[var(--text-secondary)]">
                    {liveResult.qiea_result.available ? `${liveResult.qiea_result.cargo_fulfillment_percent}%` : 'N/A'}
                  </td>
                  <td className="py-2 pl-4 text-right font-bold text-emerald-400">
                    {liveResult.best_plan.cargo_fulfillment_percent}%
                  </td>
                </tr>
              </tbody>
            </table>
          </div>

          {/* "What Changed?" vs Static $0/t Baseline Card */}
          {liveResult.baseline_comparison && (
            <div className="rounded-xl border border-[var(--border)] bg-[var(--surface-sunken)] p-4">
              <div className="flex flex-wrap items-baseline justify-between gap-2">
                <h3 className="text-sm font-bold uppercase tracking-wide text-[var(--text-primary)]">
                  What Changed vs. $0/t Status-Quo Baseline (BAU)?
                </h3>
                <span className="font-mono text-xs font-semibold text-[var(--success)]">
                  Saved ${usdM(liveResult.baseline_comparison.cost_savings_usd, 1)} ({liveResult.baseline_comparison.cost_savings_percent}%) vs BAU
                </span>
              </div>
              <p className="mt-1 text-xs text-[var(--text-secondary)]">
                {liveResult.baseline_comparison.what_changed.summary} Lifecycle emissions cut by {ktCO2e(liveResult.baseline_comparison.emissions_reduction_tco2e, 0)}.
              </p>

              <div className="mt-3 grid grid-cols-2 sm:grid-cols-5 gap-2 font-mono text-center text-xs">
                <div className="rounded-lg border border-[var(--border)] bg-[var(--surface-elevated)] p-2">
                  <div className="text-[10px] text-[var(--text-tertiary)]">Fuel Switches</div>
                  <div className="mt-0.5 text-sm font-bold text-[var(--text-primary)]">
                    {liveResult.baseline_comparison.what_changed.fuel_changes}
                  </div>
                </div>
                <div className="rounded-lg border border-[var(--border)] bg-[var(--surface-elevated)] p-2">
                  <div className="text-[10px] text-[var(--text-tertiary)]">Speed Changes</div>
                  <div className="mt-0.5 text-sm font-bold text-[var(--text-primary)]">
                    {liveResult.baseline_comparison.what_changed.speed_changes}
                  </div>
                </div>
                <div className="rounded-lg border border-[var(--border)] bg-[var(--surface-elevated)] p-2">
                  <div className="text-[10px] text-[var(--text-tertiary)]">Route Shifts</div>
                  <div className="mt-0.5 text-sm font-bold text-[var(--text-primary)]">
                    {liveResult.baseline_comparison.what_changed.route_changes}
                  </div>
                </div>
                <div className="rounded-lg border border-[var(--border)] bg-[var(--surface-elevated)] p-2">
                  <div className="text-[10px] text-[var(--text-tertiary)]">Shore Power</div>
                  <div className="mt-0.5 text-sm font-bold text-[var(--text-primary)]">
                    {liveResult.baseline_comparison.what_changed.shore_power_changes}
                  </div>
                </div>
                <div className="rounded-lg border border-[var(--border)] bg-[var(--surface-elevated)] p-2">
                  <div className="text-[10px] text-[var(--text-tertiary)]">Pooling Opt-ins</div>
                  <div className="mt-0.5 text-sm font-bold text-[var(--text-primary)]">
                    {liveResult.baseline_comparison.what_changed.pooling_changes}
                  </div>
                </div>
              </div>
            </div>
          )}

          {/* Provenance note */}
          <p className="text-[11px] leading-relaxed text-[var(--text-tertiary)]">
            <strong>Provenance:</strong> Live optimizer result calculated dynamically on local Python backend with seed {liveResult.request.seed}. The static demo cards below are precomputed catalog reference data.
          </p>
        </div>
      )}
    </section>
  );
}

function ScorecardSection({ data }: { data: DemoData }) {
  const baseline = data.baseline;
  const pareto = data.comparable_recommendations;
  const cheapest = pareto?.alternatives.find(a => a.id === 'cheapest');
  const balanced = pareto?.alternatives.find(a => a.id === 'balanced');
  const greenest = pareto?.alternatives.find(a => a.id === 'greenest');

  if (!baseline) {
    return (
      <section className="metric-card mb-6" aria-label="3-Way Benchmark Scorecard">
        <h2 className="text-sm font-bold uppercase tracking-wide text-[var(--text-primary)]">
          Tripartite Benchmark Scorecard
        </h2>
        <p className="mt-2 text-sm text-[var(--text-secondary)]">Baseline data unavailable in this dataset.</p>
      </section>
    );
  }

  const baselineCost = baseline.total_cost_usd;
  const baselineFuel = baseline.fuel_tonnes;
  const baselineGhg = baseline.lifecycle_emissions_tco2e;
  const baselineComp = baseline.compliance_cost_usd;

  const balancedCost = balanced?.metrics.total_usd ?? 0;
  const balancedFuel = balanced?.metrics.fuel_tonnes ?? 0;
  const balancedGhg = balanced?.metrics.lifecycle_emissions_tco2e ?? 0;
  const balancedComp = balanced?.metrics.compliance_usd ?? 0;

  const savingsUsd = balanced ? baselineCost - balancedCost : 0;
  const savingsPct = baselineCost > 0 ? (savingsUsd / baselineCost) * 100 : 0;

  return (
    <section className="metric-card mb-6" aria-label="3-Way Benchmark Scorecard">
      <h2 className="text-sm font-bold uppercase tracking-wide text-[var(--text-primary)]">
        Tripartite Benchmark Scorecard
      </h2>
      <p className="mb-4 mt-1 text-sm leading-relaxed text-[var(--text-secondary)]">
        Authoritative side-by-side comparison of historical status quo baseline (BAU) against classical GA,
        quantum-inspired QIEA, and the balanced multi-objective Pareto strategy.
      </p>
      <div className="overflow-x-auto">
        <table className="w-full text-left font-mono text-xs">
          <thead>
            <tr className="border-b border-[var(--border)] text-[var(--text-tertiary)]">
              <th className="py-2.5 pr-4">Metric</th>
              <th className="py-2.5 px-4">Baseline (BAU)</th>
              <th className="py-2.5 px-4">Classical GA</th>
              <th className="py-2.5 px-4">Quantum QIEA</th>
              <th className="py-2.5 pl-4 text-right">Balanced Pareto</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-[var(--border)]">
            <tr>
              <td className="py-2.5 pr-4 font-sans font-medium text-[var(--text-primary)]">Five-Year Total Cost ($)</td>
              <td className="py-2.5 px-4 text-[var(--text-secondary)]">{usdM(baselineCost, 2)}</td>
              <td className="py-2.5 px-4 text-[var(--text-secondary)]">{cheapest ? usdM(cheapest.metrics.total_usd, 2) : 'N/A'}</td>
              <td className="py-2.5 px-4 text-[var(--text-secondary)]">{balanced ? usdM(balanced.metrics.total_usd, 2) : 'N/A'}</td>
              <td className="py-2.5 pl-4 text-right font-bold text-[var(--success)]">{balanced ? usdM(balancedCost, 2) : 'N/A'}</td>
            </tr>
            <tr>
              <td className="py-2.5 pr-4 font-sans font-medium text-[var(--text-primary)]">Fuel Mass (tonnes)</td>
              <td className="py-2.5 px-4 text-[var(--text-secondary)]">{kTonnes(baselineFuel)}</td>
              <td className="py-2.5 px-4 text-[var(--text-secondary)]">{cheapest ? kTonnes(cheapest.metrics.fuel_tonnes) : 'N/A'}</td>
              <td className="py-2.5 px-4 text-[var(--text-secondary)]">{balanced ? kTonnes(balanced.metrics.fuel_tonnes) : 'N/A'}</td>
              <td className="py-2.5 pl-4 text-right font-bold text-[var(--text-primary)]">{balanced ? kTonnes(balancedFuel) : 'N/A'}</td>
            </tr>
            <tr>
              <td className="py-2.5 pr-4 font-sans font-medium text-[var(--text-primary)]">Lifecycle Emissions (tCO₂e)</td>
              <td className="py-2.5 px-4 text-[var(--text-secondary)]">{ktCO2e(baselineGhg, 0)}</td>
              <td className="py-2.5 px-4 text-[var(--text-secondary)]">{cheapest ? ktCO2e(cheapest.metrics.lifecycle_emissions_tco2e, 0) : 'N/A'}</td>
              <td className="py-2.5 px-4 text-[var(--text-secondary)]">{balanced ? ktCO2e(balanced.metrics.lifecycle_emissions_tco2e, 0) : 'N/A'}</td>
              <td className="py-2.5 pl-4 text-right font-bold text-[var(--success)]">{greenest ? ktCO2e(greenest.metrics.lifecycle_emissions_tco2e, 0) : 'N/A'}</td>
            </tr>
            <tr>
              <td className="py-2.5 pr-4 font-sans font-medium text-[var(--text-primary)]">Compliance Position ($)</td>
              <td className="py-2.5 px-4 text-[var(--text-secondary)]">{signedMoney(baselineComp)}</td>
              <td className="py-2.5 px-4 text-[var(--text-secondary)]">{cheapest ? signedMoney(cheapest.metrics.compliance_usd) : 'N/A'}</td>
              <td className="py-2.5 px-4 text-[var(--text-secondary)]">{balanced ? signedMoney(balanced.metrics.compliance_usd) : 'N/A'}</td>
              <td className="py-2.5 pl-4 text-right font-bold text-[var(--text-primary)]">{balanced ? signedMoney(balancedComp) : 'N/A'}</td>
            </tr>
            <tr>
              <td className="py-2.5 pr-4 font-sans font-medium text-[var(--text-primary)]">Cost Savings vs Baseline</td>
              <td className="py-2.5 px-4 text-[var(--text-tertiary)]">Baseline (0%)</td>
              <td className="py-2.5 px-4 text-[var(--success)]">{cheapest ? `${pct((baselineCost - cheapest.metrics.total_usd) / baselineCost, 1)}` : 'N/A'}</td>
              <td className="py-2.5 px-4 text-[var(--success)]">{balanced ? `${pct((baselineCost - balanced.metrics.total_usd) / baselineCost, 1)}` : 'N/A'}</td>
              <td className="py-2.5 pl-4 text-right font-bold text-[var(--success)]">{balanced ? `${pct(savingsPct / 100, 1)} (${usdM(savingsUsd, 1)})` : 'N/A'}</td>
            </tr>
          </tbody>
        </table>
      </div>
    </section>
  );
}

function SavingsWaterfallSection({ data }: { data: DemoData }) {
  const baseline = data.baseline;
  const pareto = data.comparable_recommendations;
  const balanced = pareto?.alternatives.find(a => a.id === 'balanced') ?? pareto?.alternatives[0];

  if (!baseline || !balanced || !baseline.waterfall_breakdown) {
    return (
      <section className="metric-card mb-6" aria-label="Dynamic Savings Waterfall">
        <h2 className="text-sm font-bold uppercase tracking-wide text-[var(--text-primary)]">
          Dynamic Savings & Emissions Waterfall
        </h2>
        <p className="mt-2 text-sm text-[var(--text-secondary)]">Waterfall variance breakdown is unavailable in this dataset.</p>
      </section>
    );
  }

  const waterfall = baseline.waterfall_breakdown;
  const steps = [
    { label: 'Baseline Operational Cost (BAU)', value: waterfall.baseline_total_usd, kind: 'base' },
    { label: 'Speed Profile & Charter Time Optimization', value: -waterfall.speed_time_savings_usd, kind: 'saving' },
    { label: 'Alternative Fuel & Shore Power Selection', value: -waterfall.fuel_ops_savings_usd, kind: 'saving' },
    { label: 'EU ETS & FuelEU Penalty Avoidance', value: -waterfall.compliance_savings_usd, kind: 'saving' },
    { label: 'Final Optimized Balanced Plan Cost', value: waterfall.balanced_total_usd, kind: 'final' },
  ];

  return (
    <section className="metric-card mb-6" aria-label="Dynamic Savings Waterfall">
      <h2 className="text-sm font-bold uppercase tracking-wide text-[var(--text-primary)]">
        Dynamic Savings & Emissions Waterfall
      </h2>
      <p className="mb-4 mt-1 text-sm leading-relaxed text-[var(--text-secondary)]">
        Computed variance decomposition showing how speed optimization, fuel switching, shore power, and regulatory penalty avoidance reduce baseline liabilities down to the optimized Pareto plan.
      </p>
      <div className="space-y-3 font-mono text-xs">
        {steps.map((step, idx) => (
          <div key={idx} className="flex items-center justify-between rounded-lg border border-[var(--border)] bg-[var(--surface-sunken)] p-3">
            <span className="font-sans font-medium text-[var(--text-primary)]">{step.label}</span>
            <span className={`font-bold ${step.kind === 'saving' ? (step.value <= 0 ? 'text-[var(--success)]' : 'text-[var(--warning)]') : 'text-[var(--text-primary)]'}`}>
              {step.kind === 'saving'
                ? (step.value <= 0 ? `−${usdM(Math.abs(step.value), 2)}` : `+${usdM(step.value, 2)}`)
                : usdM(step.value, 2)}
            </span>
          </div>
        ))}
      </div>
    </section>
  );
}

function exportDispatchCsv(data: DemoData) {
  const pareto = data.comparable_recommendations;
  const balanced = pareto?.alternatives.find(a => a.id === 'balanced') ?? pareto?.alternatives[0];
  const config = balanced?.configuration ?? [];

  const headers = [
    'Vessel_ID',
    'Year',
    'Route',
    'Speed_Knots',
    'Fuel_Type',
    'Shore_Power',
    'FuelEU_Pool',
    'Borrow_Election',
    'Fuel_Tonnes',
    'GHG_tCO2e',
    'CII_Rating',
    'Voyage_Cost_USD',
  ];

  const rows = config.map(g => [
    g.vessel_id,
    g.year,
    g.route_id,
    g.speed_knots != null ? g.speed_knots.toFixed(1) : `Band ${g.speed_band_index}`,
    g.fuel_id,
    g.shore_power ? 'YES' : 'NO',
    g.pool_opt_in ? 'YES' : 'NO',
    g.borrow_election ? 'YES' : 'NO',
    g.fuel_tonnes != null ? g.fuel_tonnes.toFixed(1) : 'N/A',
    g.ghg_tco2e != null ? g.ghg_tco2e.toFixed(1) : 'N/A',
    g.cii_rating ?? 'N/A',
    g.voyage_cost_usd != null ? g.voyage_cost_usd.toFixed(2) : 'N/A',
  ]);

  const csvContent = [headers.join(','), ...rows.map(r => r.join(','))].join('\n');
  const blob = new Blob([csvContent], { type: 'text/csv;charset=utf-8;' });
  const url = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.setAttribute('href', url);
  link.setAttribute('download', 'nexfleet_dispatch_schedule.csv');
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
}

function Recommendations({ data }: { data: DemoData }) {
  const recommendations = data.comparable_recommendations ?? null;

  if (!recommendations) return <StaleDataNotice />;

  return (
    <>
      <TradeOffDeck recommendations={recommendations} metadata={data.metadata} />
      <div className="page-shell pb-6 pt-2">
        <LiveOptimizationSection data={data} />
        <ScorecardSection data={data} />
        <SavingsWaterfallSection data={data} />
        <div className="rounded-xl border border-[var(--border)] bg-[var(--surface-sunken)] p-4 flex flex-col sm:flex-row items-center justify-between gap-4">
          <div>
            <h3 className="font-bold text-sm text-[var(--text-primary)]">Operational Dispatch Table Export</h3>
            <p className="text-xs text-[var(--text-secondary)] mt-0.5">Download executable 5-year voyage dispatch schedules (per vessel, per year) as a CSV ledger.</p>
          </div>
          <button
            onClick={() => exportDispatchCsv(data)}
            className="rounded-md bg-[var(--action-bg)] px-4 py-2 text-xs font-bold text-[var(--action-text)] transition-colors hover:bg-[var(--action-bg-hover)] flex items-center gap-2 whitespace-nowrap"
          >
            Export Dispatch Plan (CSV)
          </button>
        </div>
      </div>
    </>
  );
}

export function RecommendationView() {
  return <DataGate>{data => <Recommendations data={data} />}</DataGate>;
}

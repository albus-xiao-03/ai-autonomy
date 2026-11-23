"""Live hybrid runs: launch, lookup, reset and cancel, with run isolation and per-run locks.

Every run has its own state, records, epoch and lock; nothing is shared between runs except
the read-only map store and catalogs. A reset records the old run as interrupted and starts a
new run (new id, epoch + 1) from the same launch setup, so late work for the old run can only
be rejected. Ended runs beyond `max_live` are dropped from memory (their records stay on disk).

REQ: SIM-05, CITY-04, CITY-05, END-05
"""

import asyncio
from collections.abc import Callable, Sequence
from pathlib import Path

from aiautonomy.engines.contract.common import MayorBackend
from aiautonomy.engines.contract.runs import RunLaunchRequest
from aiautonomy.engines.core.datafiles import DataFileError, DataFileRef
from aiautonomy.engines.hybrid import disruptions
from aiautonomy.engines.hybrid.catalogs import Catalogs, load_catalogs
from aiautonomy.engines.hybrid.errors import RunError
from aiautonomy.engines.hybrid.run import HybridRun, HybridSink, RunSetup
from aiautonomy.engines.mayor.backends import api_available
from aiautonomy.engines.mayor.providers import (
    ApiProvider,
    BaselineProvider,
    LocalProvider,
    MayorProvider,
)
from aiautonomy.engines.residents.llm import LocalResidentProvider, ResidentProvider
from aiautonomy.engines.sim.config import (
    InferenceSettings,
    RunOverrides,
    load_inference_settings,
    resolve_run_config,
)
from aiautonomy.engines.world.boston import BostonWorldConfig
from aiautonomy.engines.world.map_store import MapStore
from aiautonomy.engines.world.maps import CANONICAL_CATALOG, canonical_catalog

DEFAULT_MAX_LIVE = 16


def default_provider(backend: MayorBackend, inference: InferenceSettings) -> MayorProvider:
    """The mayor provider for a backend, with the engine-configured models.

    The API mayor is refused unless the engine runs with the paid-API interlock.
    """
    if backend == "local":
        return LocalProvider(inference.mayor_local_model, inference.mayor_wait_s)
    if backend == "api":
        if not api_available():
            raise RunError(
                409,
                "paid_api_disabled",
                "the API mayor needs AIA_ALLOW_PAID_API=1 and ANTHROPIC_API_KEY on the engine",
            )
        return ApiProvider(inference.mayor_api_model)
    return BaselineProvider()


def default_resident_provider(inference: InferenceSettings) -> ResidentProvider:
    """Residents always use local Ollama with the engine-configured model (LOCAL-01)."""
    return LocalResidentProvider(
        inference.resident_model, inference.resident_wait_s, inference.resident_model_digest
    )


class RunStore:
    def __init__(
        self,
        maps: MapStore,
        root: Path,
        *,
        new_run_id: Callable[[str, int], str],
        sinks: Callable[[], Sequence[HybridSink]] = list,
        max_live: int = DEFAULT_MAX_LIVE,
        providers: Callable[[MayorBackend, InferenceSettings], MayorProvider] = default_provider,
        inference: InferenceSettings | None = None,
        resident_providers: Callable[
            [InferenceSettings], ResidentProvider
        ] = default_resident_provider,
        catalogs: Catalogs | None = None,
    ) -> None:
        self.maps = maps
        self.root = root
        self.new_run_id = new_run_id
        self.sinks = sinks
        self.max_live = max_live
        self.providers = providers
        self.inference = inference
        self.resident_providers = resident_providers
        self.catalogs = catalogs
        self.runs: dict[str, HybridRun] = {}
        self._locks: dict[str, asyncio.Lock] = {}

    def setup(self, request: RunLaunchRequest) -> RunSetup:
        """Resolve and validate everything a launch needs; nothing is created on failure."""
        revision = self.maps.resolve(request.map)
        report, _ = self.maps.validate(revision.content, None, [])
        if not report.ok:
            raise RunError(422, "map_invalid", "the pinned map is not valid", report.failures)
        overrides = RunOverrides(
            scenario=request.scenario,
            seed=request.seed,
            duration=request.duration,
            population=request.population,
            llm_ratio_bp=request.llm_ratio_bp,
        )
        try:
            resolved = resolve_run_config(overrides, root=self.root)
        except (DataFileError, ValueError) as exc:
            raise RunError(422, "invalid_scenario", str(exc)) from exc
        if not isinstance(resolved.config.world, BostonWorldConfig):
            message = f"{request.scenario!r} is not a hybrid scenario"
            raise RunError(422, "invalid_scenario", message)
        catalog = canonical_catalog(self.root)
        map_ref = DataFileRef(
            id=revision.id,
            version=revision.revision,
            schema_version=revision.format_version,
            path=f"maps:{revision.id}/r{revision.revision}",
            sha256=revision.sha256,
        )
        canonical_ref = DataFileRef(
            id=catalog.catalog.id,
            version=catalog.catalog.version,
            schema_version=catalog.catalog.schema_version,
            path=CANONICAL_CATALOG.as_posix(),
            sha256=catalog.sha256,
        )
        try:
            catalogs = self.catalogs or load_catalogs(self.root)
        except (DataFileError, ValueError) as exc:
            raise RunError(422, "invalid_catalog", str(exc)) from exc
        bounds = catalog.catalog.bounds(revision.content.level)
        failures = [
            failure
            for index, spec in enumerate(request.disruptions.scheduled)
            for failure in disruptions.check_spec(
                spec,
                earliest=disruptions.FIRST_START_TICK,
                duration=resolved.config.duration,
                bounds=bounds,
                entity=f"scheduled[{index}]",
                require_tick=True,
            )
        ]
        if failures:
            raise RunError(422, failures[0].code, "a scheduled disruption is not valid", failures)
        inference = self.inference or load_inference_settings(self.root)
        return RunSetup(
            request=request,
            config=resolved.config,
            data_files=(*resolved.data_files, canonical_ref, *catalogs.refs, map_ref),
            map_revision=revision,
            catalogs=catalogs,
            bounds=bounds,
            inference=inference,
        )

    def launch(self, request: RunLaunchRequest) -> HybridRun:
        setup = self.setup(request)
        self.providers(request.mayor_backend, setup.inference)  # refuse before recording
        return self._start(setup, run_epoch=1)

    def _start(self, setup: RunSetup, run_epoch: int) -> HybridRun:
        run_id = self.new_run_id(setup.config.scenario, setup.config.seed)
        provider = self.providers(setup.request.mayor_backend, setup.inference)
        run = HybridRun(
            setup,
            run_id=run_id,
            run_epoch=run_epoch,
            sinks=self.sinks(),
            provider=provider,
            resident_provider=self.resident_providers(setup.inference),
        )
        self.runs[run_id] = run
        self._evict()
        return run

    def get(self, run_id: str) -> HybridRun:
        run = self.runs.get(run_id)
        if run is None:
            raise RunError(404, "unknown_run", f"no live run {run_id!r}")
        return run

    def lock(self, run_id: str) -> asyncio.Lock:
        """The lock that serializes one run's ticks and decisions."""
        if run_id not in self._locks:
            self._locks[run_id] = asyncio.Lock()
        return self._locks[run_id]

    def _check_epoch(self, run: HybridRun, run_epoch: int) -> None:
        if run_epoch != run.run_epoch:
            raise RunError(
                409, "stale_epoch", f"run {run.run_id} is at epoch {run.run_epoch}, not {run_epoch}"
            )

    def reset(self, run_id: str, run_epoch: int) -> HybridRun:
        """Interrupt the run and start the next epoch from the same launch setup."""
        old = self.get(run_id)
        self._check_epoch(old, run_epoch)
        old.interrupt("reset by the game")
        return self._start(old.setup, run_epoch=old.run_epoch + 1)

    def cancel(self, run_id: str, run_epoch: int) -> HybridRun:
        run = self.get(run_id)
        self._check_epoch(run, run_epoch)
        run.interrupt("cancelled by the game")
        return run

    def shutdown(self) -> None:
        """Engine shutdown: unfinished runs are recorded as interrupted (END-05)."""
        for run in self.runs.values():
            run.interrupt("engine shutdown")

    def _evict(self) -> None:
        ended = [run_id for run_id, run in self.runs.items() if run.status != "running"]
        while len(self.runs) > self.max_live and ended:
            run_id = ended.pop(0)
            del self.runs[run_id]
            self._locks.pop(run_id, None)

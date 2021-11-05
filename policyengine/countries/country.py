from pathlib import Path
from typing import Callable, Dict, Tuple, Type
from openfisca_tools.model_api import ReformType
import yaml
from openfisca_core.taxbenefitsystems.tax_benefit_system import (
    TaxBenefitSystem,
)
from policyengine.impact.population.revenue_breakdown import (
    get_breakdown_per_provision,
)
from policyengine.utils.general import (
    PolicyEngineResultsConfig,
    exclude_from_cache,
)
from openfisca_tools import Microsimulation, IndividualSim
from policyengine.countries.entities import build_entities
from policyengine.impact.household.charts import (
    budget_chart,
    household_waterfall_chart,
    mtr_chart,
)
from policyengine.impact.household.metrics import headline_figures, variable_changes
from policyengine.impact.population.metrics import headline_metrics
from policyengine.impact.population.charts import (
    decile_chart,
    poverty_chart,
    population_waterfall_chart,
    intra_decile_chart,
)
from policyengine.utils.reforms import (
    add_parameter_file,
    create_reform,
    get_PE_parameters,
    use_current_parameters,
)
from policyengine.utils.situations import create_situation, get_PE_variables


class PolicyEngineCountry:
    name: str
    system: Type[TaxBenefitSystem]
    Microsimulation: Type[Microsimulation]
    IndividualSim: Type[IndividualSim]
    default_reform: type = ()
    parameter_file: Path = None
    default_dataset: type
    default_household_file: Path
    entity_hierarchy_file: Path
    version: str

    results_config: Type[PolicyEngineResultsConfig]

    def __init__(self):
        self.default_reform = (
            use_current_parameters(),
            add_parameter_file(self.parameter_file.absolute())
            if self.parameter_file is not None
            else (),
            self.default_reform,
        )

        self.baseline = self.Microsimulation(
            self.default_reform, dataset=self.default_dataset
        )

        self.baseline.simulation.trace = True
        self.baseline.calc("net_income")

        self.policyengine_parameters = get_PE_parameters(
            self.baseline.simulation.tax_benefit_system
        )

        self.policyengine_variables = get_PE_variables(
            self.baseline.simulation.tax_benefit_system
        )

        self.api_endpoints = dict(
            household_reform=self.household_reform,
            population_reform=self.population_reform,
            ubi=self.ubi,
            parameters=self.parameters,
            entities=self.entities,
            variables=self.variables,
            default_household=self.default_household,
            population_breakdown=self.population_breakdown,
        )
        with open(self.entity_hierarchy_file) as f:
            self.entities = dict(
                entities=build_entities(
                    self.baseline.simulation.tax_benefit_system
                ),
                hierarchy=yaml.safe_load(f),
            )

        with open(self.default_household_file) as f:
            self.default_household_data = yaml.safe_load(f)

    def _create_reform_sim(self, params: dict) -> Microsimulation:
        sim = self.Microsimulation(
            (self.default_reform, create_reform(params, self.policyengine_parameters)), dataset=self.default_dataset
        )
        sim.simulation.trace = True
        sim.calc("net_income")
        return sim

    def population_reform(self, params: dict = None):
        reformed = self._create_reform_sim(params)
        return dict(
            **headline_metrics(self.baseline, reformed, self.results_config),
            decile_chart=decile_chart(
                self.baseline, reformed, self.results_config
            ),
            poverty_chart=poverty_chart(
                self.baseline, reformed, self.results_config
            ),
            waterfall_chart=population_waterfall_chart(
                self.baseline, reformed, self.results_config
            ),
            intra_decile_chart=intra_decile_chart(
                self.baseline, reformed, self.results_config
            ),
        )

    def _create_situation(self, params: dict) -> Callable:
        return create_situation(
            params["household"],
            ["household"],
            self.entities["hierarchy"],
            self.entities["entities"],
        )
    
    def _create_baseline_household_sim(self, params: dict, situation = None) -> IndividualSim:
        if situation is None:
            situation = self._create_situation(params)
        baseline_config = self.default_reform
        return situation(
            self.IndividualSim(baseline_config, year=2021)
        )
    
    def _create_reform_household_sim(self, params: dict, situation = None, reform = None) -> IndividualSim:
        if situation is None:
            situation = self._create_situation(params)
        if reform is None:
            reform = create_reform(params, self.policyengine_parameters)
        reform_config = self.default_reform, reform
        return situation(
            self.IndividualSim(reform_config, year=2021)
        )


    @exclude_from_cache
    def household_reform(self, params=None):
        with open("household_params.yaml", "w+") as f:
            yaml.dump(params, f)
        situation = self._create_situation(params)
        reform = create_reform(params, self.policyengine_parameters)
        baseline = self._create_baseline_household_sim(params, situation)
        reformed = self._create_reform_household_sim(params, situation, reform)
        baseline.calc("net_income")
        reformed.calc("net_income")
        baseline_extra_earnings = self._create_baseline_household_sim(params, situation)
        baseline_extra_earnings.calc("employment_income")
        baseline_extra_earnings.simulation.set_input("employment_income", 2021, baseline.calc("employment_income") + 1)
        reformed_extra_earnings = self._create_reform_household_sim(params, situation, reform)
        reformed_extra_earnings.calc("employment_income")
        reformed_extra_earnings.simulation.set_input("employment_income", 2021, reformed.calc("employment_income") + 1)
        headlines = headline_figures(baseline, reformed, self.results_config)
        waterfall = household_waterfall_chart(
            baseline, reformed, self.results_config
        )
        variables = variable_changes(baseline, reformed, baseline_extra_earnings, reformed_extra_earnings)
        baseline.vary("employment_income", step=100)
        reformed.vary("employment_income", step=100)
        budget = budget_chart(baseline, reformed, self.results_config)
        mtr = mtr_chart(baseline, reformed, self.results_config)
        return dict(
            **headlines,
            waterfall_chart=waterfall,
            budget_chart=budget,
            mtr_chart=mtr,
            variables=variables,
        )

    def ubi(self, params=None):
        reform = create_reform(params, self.policyengine_parameters)
        reformed = self.Microsimulation(
            (self.default_reform, reform), dataset=self.default_dataset
        )
        revenue = (
            self.baseline.calc(self.results_config.net_income_variable).sum()
            - reformed.calc(self.results_config.net_income_variable).sum()
        )
        UBI_amount = max(
            0,
            revenue
            / self.baseline.calc(self.results_config.person_variable).sum(),
        )
        return {"UBI": float(UBI_amount)}

    @exclude_from_cache
    def parameters(self, params=None):
        return self.policyengine_parameters

    @exclude_from_cache
    def entities(self, params=None):
        return self.entities

    @exclude_from_cache
    def variables(self, params=None):
        return self.policyengine_variables

    @exclude_from_cache
    def default_household(self, params=None):
        return self.default_household_data

    def population_breakdown(self, params=None):
        reform, provisions = create_reform(
            params, self.policyengine_parameters, return_descriptions=True
        )
        return get_breakdown_per_provision(
            reform, provisions, self.baseline, self._create_reform_sim
        )

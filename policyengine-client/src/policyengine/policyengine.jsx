/*
 * The main component for PolicyEngine-[Country]
 */

import React from "react";
import { Navigate, Route, Routes } from "react-router-dom";
import { CountryContext, UK, US } from "../countries";
import { Header } from "./header";
import { Footer } from "./footer";
import { BodyWrapper, PolicyEngineWrapper } from "./layout/general";
import { Policy } from "./pages/policy";
import { policyToURL, urlToPolicy } from "./tools/url";
import { PopulationImpact } from "./pages/populationImpact";
import FAQ from "./pages/markdown";
import { Household } from "./pages/household";
import Centered from "./general/centered";
import Spinner from "./general/spinner";
import APIExplorer from "./pages/apiExplorer";

export default class PolicyEngine extends React.Component {
  constructor(props) {
    super(props);
    this.prepareData = this.prepareData.bind(this);
    let country = { uk: new UK(), us: new US() }[props.country];
    country.stateHolder = this;
    country.analytics = props.analytics;
    this.state = { country: country };
  }

  setCountryState(data, callback) {
    let country = this.state.country;
    for (let key of Object.keys(data)) {
      country[key] = data[key];
    }
    this.setState({ country: country }, callback);
  }

  prepareData() {
    // Once data is fetched, apply some adjustments to the OpenFisca data
    // (that we don't want to apply in OpenFisca-[Country] because they're not
    // legislative)
    let { policy } = this.state.country.validatePolicy(
      urlToPolicy(
        this.state.country.parameters,
        this.state.country.parameterRenames
      ),
      this.state.country.parameters
    );
    for (let parameter of Object.keys(policy)) {
      if (
        Object.keys(this.state.country.extraParameterMetadata).includes(
          parameter
        )
      ) {
        policy[parameter] = Object.assign(
          policy[parameter],
          this.state.country.extraParameterMetadata[parameter]
        );
      }
    }
    let variables = this.state.country.variables;
    for (let variable of Object.keys(variables)) {
      if (
        Object.keys(this.state.country.extraVariableMetadata).includes(variable)
      ) {
        variables[variable] = Object.assign(
          variables[variable],
          this.state.country.extraVariableMetadata[variable]
        );
      }
    }
    const situation = this.state.country.validateSituation(
      this.state.country.situation
    ).situation;
    let parameters = JSON.parse(JSON.stringify(policy));
    for(let parameter in parameters) {
      parameters[parameter].value = parameters[parameter].defaultValue;
    }
    this.setCountryState({
      situation: situation,
      parameters: parameters,
      policy: JSON.parse(JSON.stringify(policy)),
      fullyLoaded: true,
    });
  }

  componentDidMount() {
    // When the page loads, fetch parameter, variables and entities, and
    // then mark as done.
    const checkAllFetchesComplete = () => {
      if (
        this.state.country.parameters !== null &&
        this.state.country.variables !== null &&
        this.state.country.entities !== null
      ) {
        this.prepareData();
      }
    };
    const parameterList = this.state.country.getParameterList();
    const fetchEndpoint = (name) => {
      let url = this.state.country.apiURL + "/" + name;
      fetch(url)
        .then((response) => response.json())
        .then((data) => {
          if (name === "parameters") {
            let filteredData = {};
            for (let storedParameter of parameterList) {
              for (let fetchedParameter in data) {
                if (fetchedParameter.includes(storedParameter)) {
                  filteredData[fetchedParameter] = data[fetchedParameter];
                }
              }
            }
            data = filteredData;
          }
          this.setCountryState({ [name]: data }, checkAllFetchesComplete);
        });
    };
    ["parameters", "variables", "entities", "endpoint-runtimes"].forEach(fetchEndpoint);
  }

  render() {
    const redirect = (from, to) => (
      <Route path={from} element={<Navigate to={to} />} />
    );

    const redirectToPolicy = (from, to) => {
      return redirect(
        from,
        policyToURL(to, urlToPolicy(this.state.country.policy))
      );
    };


    // Once fully loaded, direct onto individual pages
    if (!this.state.country.fullyLoaded) {
      return (
        <PolicyEngineWrapper>
          <CountryContext.Provider value={this.state.country}>
            <Header />
            <BodyWrapper>
              <Centered>
                <Spinner />
              </Centered>
            </BodyWrapper>
            <Footer />
          </CountryContext.Provider>
        </PolicyEngineWrapper>
      );
    }
    const countryName = this.state.country.name;
    document.title = "PolicyEngine " + this.state.country.properName;
    return (
      <PolicyEngineWrapper>
        <CountryContext.Provider value={this.state.country}>
          <Header />
          <BodyWrapper>
            <Routes>
              <Route path={`policy`} element={<Policy />} />
              <Route
                path={`population-impact`}
                element={<PopulationImpact />}
              />
              <Route path={`household`} element={<Household />} />
              <Route path={`faq`} element={<FAQ />} />
              <Route path={`api-explorer/*`} element={<APIExplorer />} />
              {/* Redirects from legacy URLs */}
              {redirectToPolicy(
                `population-results`,
                `/${countryName}/population-impact`
              )}
              {redirectToPolicy(
                `household-impact`,
                `/${countryName}/household`
              )}
              {redirectToPolicy(`situation`, `/${countryName}/household`)}
              {redirectToPolicy(
                `situation-results`,
                `/${countryName}/household`
              )}
              {redirect(`legislation`, `/${countryName}/api-explorer`)}
            </Routes>
          </BodyWrapper>
          <Footer />
        </CountryContext.Provider>
      </PolicyEngineWrapper>
    );
  }
}

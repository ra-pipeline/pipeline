# Documentation of “Docs”

This note briefly describes the updated documentation setup introduced at the end of 2024, which enables the automatic generation of Pipeline documentation from the codebase.

## General Context

[rtd]: https://about.readthedocs.com

Our documentation is categorized into three main groups:
	•	User Reference Information: guides and instructions for end-users, task reference manual, past release
	•	Developer Notes: Internal documentation, such as the page you’re currently viewing, aimed at developers.
	•	Code Examples: Practical examples and use cases showcasing the functionality of the pipeline.

## Technical Setup

The [ReadTheDocs][rtd] autobuild process is configured using a free containerized `Ubuntu` environment, with custom steps defined in the `.readthedocs.yaml` file. The sequence is as follows:
	
1.	Checkout the Repository Branch: Retrieves the specific branch of the repository to build.
2.	Install Necessary LaTeX Dependencies: Installs LaTeX-related tools required for building PDF documentation.
3.	Set Up a Custom Conda Environment: Configures a custom Python environment using the environment.yaml file in the repository branch.
4.	Install Required Python Dependencies: Installs additional packages via pip.
5.	Build HTML and PDF Documentation: Executes Sphinx commands to build the documentation artifacts.

Finally, [ReadTheDocs][rtd] ingests the generated artifacts and hosts them on the platform.

### Automation and Webhooks

Webhooks are configured between the `Open-Bitbucket@NRAO` instance and [ReadTheDocs][rtd]. This setup allows builds to be triggered automatically based on webhook events, providing flexibility in configuring conditions for these triggers.

### Sphinx Configuration and Extensions

For API documentation, we utilize Sphinx with two potential approaches:
	
1.	Namespace-Based Approach: Using sphinx.ext.autodoc with autosummary.
2.	Module-Based Approach: Using the automodapi extension.

These approaches provide flexibility in organizing API documentation, whether based on namespaces or modules, to meet the project’s requirements. Both methods are extensively customized using Jinja + RST templates, directives, and local Python code blocks, with meticulous management of namespaces, cross-module imports, and continuous enhancement of docstrings. Although the current customizations are minimal, incremental improvements are planned for the future.

[myst-nb]: https://myst-nb.readthedocs.io/en/latest/

For notebooks, we chose MyST-NB over nbsphinx due to its superior feature support and more up-to-date documentation.
Notably, several major projects have transitioned to [MyST-NB][myst-nb] over the years, making it a strong choice for both user and developer content.
It supports workflows in both .ipynb notebooks and MyST-enhanced Markdown files, offering flexibility and future-proofing.
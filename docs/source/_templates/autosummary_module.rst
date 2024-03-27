{{ fullname | escape | underline}}

.. automodule:: {{ fullname }}

{% block modules %}
{% if modules %}
.. rubric:: Pipeline Modules

.. autosummary::
   :toctree:
   :recursive:
{% for item in modules %}
{% if 'pipeline.h' in item %}
   {% set item1 = item.split('.')[-1] %}
   {{ item1 }}
{% endif %}
{%- endfor %}
{% endif %}
{% endblock %}

# Field parameter

This note aims to document how Pipeline currently handles the "field" input,
prompted by discussions on "fields", "mosaics", and future "group processing" at
the 2022 and 2023 F2F meetings, see also the tickets PIPE-1666 and PIPE-1887.

## Background info on usage of 'field' in ALMA and CASA

* The MeasurementSet v2 definition from January 2020: https://casa.nrao.edu/Memos/229.html
specifies the following: fields are stored in the MeasurementSet in the FIELD table.
The field ID is implicitly set by the row number, while field name is an explicit
column NAME, with value specified by the PI. The table also supports a SOURCE_ID
column to point each field to an entry in the optional SOURCE subtable.

* In the MS v3 definition, the field ID is proposed to become an explicit FIELD_ID
column, see beta MS v3 from July 2019: https://casacore.github.io/casacore-notes/264.html

* "field" is one of the key data selection parameters in CASA tasks, alongside spw.

* In ALMA datasets, field names are not guaranteed to be unique, i.e. there
can be multiple fields (with different field IDs) present that share the same field
name. As such, selecting data or storing data based on just field name is usually
not safe to do.

* CASA tasks accept 'field' as a string that may contain a mix of field ID integers
and/or field names; it includes regular expression syntax that means that
certain special characters should not be part of a field name.
  * As a consequence of accepting field IDs, CASA cannot accept a field name
  that's purely numerical. For reference, see the note at the bottom of "field"
  section at https://casadocs.readthedocs.io/en/stable/notebooks/visibility_data_selection.html#The-field-Parameter.

* In the ALMA Observing Tool (OT), a mosaic can be defined in two ways:
  1. for a given source, one can set target type = "rectangular field", resulting
  in OT generating a series of pointings representing a rectangular mosaic of
  spatially contiguous pointings around the source; or
  2. for a given source, one can set target type to "multiple pointings" where
  the user can manually define a series of pointings around the source, though
  OT will force the user to define pointings that still connect together as 
  belonging to the same source (it'll complain if the pointings are unconnected
  / too far apart).

* In an ALMA observational dataset, these mosaics will show up as a series of
fields that all cover TARGET intent and all share the same field name (related
to what the PI entered as the source name) but with different IDs and pointings.
Pipeline currently (as of 2023 release) does not have an entity to represent
this as a mosaic. Field names are not guaranteed to be uniquely used by just that
science target; there have been examples where the same field name, but with
different id and/or coordinates, is also covered by different intent scans.

* In ALMA Single-Dish, there is a distinction between on-source and off-source,
but these normally have the same field name, and are also observed in the same
scans. Any potential refactoring of handling of identifying field should take
this into account.

## Definition of Field in Pipeline
Pipeline has defined a Field domain class in pipeline.domain.field.Field, including
the attributes:
* name: str,  populated from msmd.namesforfields()
* id: int,  populated by range(msmd.nfields())
* intents: list,  populated based on msmd.statesforscans() or source_type

Since before 2013, PL has internally used for field.name the CASA-safe field name
(uses double-quote in presence of illegal chars).

Since 2015 (CAS-7295), the internal field.name also converts “digits-only” to
CASA-safe names (i.e. wrap in double quote).

Consequence: any user-provided values for “field” should be made CASA-safe (if
it isn’t already) before field name comparisons.

### Conversion of 'field' names for CASA

Pipeline includes two conversion utility functions to convert any given field
name to a "CASA-safe" field name.

* infrastructure/utils/utils.py: fieldname_for_casa(field: str) -> str

  This returns a string with field name in double quotes if field name was
  numerical or contains special characters; otherwise returns unchanged.

* infrastructure/utils/dequote.py: dequote(s: str) -> str

  Conversion utility to remove safety quotes from field names; removes any
  occurrence of " or '.

## Use-case for 'field' in Pipeline

### 'field' as a input parameter to select visibility data 
Pipeline predominantly operates on data that is selected based on "intent", e.g.
create a bandpass correction from scans taken with the BANDPASS intent.

There are a number of Pipeline tasks that expose "field" as an input parameter.
For these, field is set by default to an empty string to signify that it will be
automatically populated based on intent (and MS being processed), but "field" is
available for user-override.

The use-case for what should happen when a user overrides the "field" parameter
will naturally vary from task to task, and this behaviour is currently not
always explicitly specified or documented. For example, hifa_timegaincal comprises
multiple gaincal steps that each operate on a separate set of intents (that determine
what "field" should be), yet the task only supports a single "intent" and "field" input
parameter. As such, it is not specified what the task should do if a crucial field
is explicitly left out (presently, this likely leads to a failure to create a
necessary caltable).

The following is a non-exhaustive list of Pipeline tasks that support a public
"field" input parameter:
* [h*]_applycal
* hsd_atmcor
* hsd_blflag
* hif_correctedampflag
* hif_editimlist
* hif_makeimlist
* hif_mstransform
* hif_refant
* hif_setjy
* hifa_bpsolint
* hifa_fluxcalflag
* hifa_gaincalsnr
* hifa_gfluxscaleflag
* hifv_vlasetjy
* hifa_gfluxscale  (calls it "transfer" instead of "field")

By contrast, there are a couple of tasks that do not expose "field", including:
* hif_lowgainflag
* hif_rawflagchans
* [h*]_tsysflag

## Heuristics to derive field from intent
When selecting what data to operate on, most (if not all) Pipeline tasks need to
convert an "intent" to a list of fields. This conversion from "intent" to "field"
is currently implemented in individual tasks, typically in the definition
of default value of "field" in the task Inputs class. There are different approaches
taken by different tasks, and it is not clear if that was always intentional. 
There is potentially scope to consolidate these heuristics for converting "intent"
to "field", but that will require careful validation to ensure it's not changing
behaviour in a way that is undesired.

The following aims to summarize the different heuristics that are presently in
use in Pipeline:

### Intent-to-field pattern 1:

    field_finder = IntentFieldnames()
    intent_fields = field_finder.calculate(self.ms, self.intent)
    fields = set()
    fields.update(utils.safe_split(intent_fields))
    return ','.join(fields) 

Used by:
* h_applycal
* hsd_atmcor
* hsd_blflag
* hif.tasks.common.commoncalinputs.VdpCommonCalibrationInputs

This uses a "common" field finder heuristic from module
h.heuristics.fieldnames.IntentFieldnames, with the key selection happening in:

          identifiers = []
          for field in fields:
            with_intent = ms.get_fields(name=[field.name], intent=intent)
            any_intent = ms.get_fields(name=[field.name])
            if len(with_intent) == len(any_intent):
                identifiers.append(field.name)
            else:
                identifiers.append(str(field.id))
        return ','.join(identifiers) 

This common heuristic will first identify a list of fields based on the scans in
the MS that cover a given inputs.intent. Then, for each field, it is determined
if its field name uniquely appears only among the fields for given inputs.intent,
or whether the field name is also used for one of the other non-specified intents.
If the former, then it returns that field by name, otherwise it'll return it as
a string of its integer ID. Finally, the returned value is "safely split", added
to a set, and recombined into a string. The returned string can contain a mix of
field names and field IDs.

Note: IntentFieldnames does not already return a unique set; if the "intent"
parameter covers multiple intents, then there can be two or more fields (with
different IDs) that could have the same name, but each covering only one of the
intents, and for those IntentFieldnames would return the identifier twice.
This is why the above-mentioned pattern takes the extra step of converting to a
set and then back to a string.

This highlights a potential issue:
Because IntentFieldnames() currently returns all field identifiers as a comma
separated string of string values (regardless of whether the original value was
a field name or ID), the current step that consolidates the identifiers into a
unique set could do the wrong thing: If one of the field names is a short integer,
e.g. field.id=0, field.name="1", and one of the other fields was added by ID,
say field.id=1, field.name="non-unique-name", then these would show up as "1,1",
and be consolidated to just "1", thus unintentionally dropping field ID 0 in a
typical CASA task call (without double-quotes around the integer, it would
interpret "1" as field ID 1).

### Intent-to-field pattern 2:

        fields = self.ms.get_fields(intent=self.intent)
        unique_field_names = {f.name for f in fields}
        field_ids = {f.id for f in fields}
        if len(unique_field_names) == len(field_ids):
            return ','.join(unique_field_names)
        else:
            return ','.join([str(i) for i in field_ids]) 

Used by:
* infrastructure.callibrary.CalToIdAdapter
* hif_refant
* hifv_vlasetjy
* hif_uvcontfit
* hif_setjy

This approach identifies fields for given inputs.intent, and then checks if the
number of fields by ID is the same as the number of unique field names. If so,
it returns the fields by name, but if not, it will return a string of fields by
ID (all of them). This ensures for example that a for loop over fields would
treat each field (pointing) separately, even if some share name.

### Intent-to-field pattern 3:

        fields = self.ms.get_fields(intent=self.intent)
        field_names = {f.name for f in fields}
        return ','.join(field_names) 

Used by:
* hifa_fluxcalflag
* hifa_gaincalsnr (variation)

This identifies fields for given inputs.intent, and still filters for duplicate
field names, but does not filter against any fields (by ID) that share the name
but don't cover the intent. This could potentially be an issue, unless the task
consistently also uses "intent" in conjunction to further down select.

hifa_gaincalsnr uses a more convoluted version, but appears to ultimately return
the same kind of string of unique field names.

### Intent-to-field pattern 4:

        fieldids = [field.name for field in self.ms.get_fields(intent=self.intent)]
        return ','.join(fieldids) 

Used by:
* hif_correctedampflag
* hifa_gfluxscaleflag

This returns fields for given inputs.intent, only by name (despite name of variable),
and does not filter against duplicate field names, nor does it filter against
fields (by ID) that do not cover the given intent, i.e. this may pick up fields
(by name) that cover other intents. It is possible that the remainder of the task
performs further explicit data selection by restricting to both field and intent.

### Intent-to-field pattern 5:

        fields = self.ms.get_fields(intent=self.intent)
        if fields:
            fields_by_id = sorted(fields, key=operator.attrgetter('id'))
            last_field = fields_by_id[-1]

            if getattr(last_field, 'source', None) is None:
                fields.remove(last_field)
            else:
                requested_spws = set(self.ms.get_spectral_windows(self.spw))
                if last_field.valid_spws.isdisjoint(requested_spws):
                    fields.remove(last_field)

        unique_field_names = {f.name for f in fields}
        field_ids = {f.id for f in fields}

        if len(unique_field_names) == len(field_ids):
            return ','.join(unique_field_names)
        else:
            return ','.join([str(i) for i in field_ids])

Used by:
* hif_mstransform

This is a variation on earlier patterns. It identifies fields for the given
inputs.intent, but in addition filters out the last field (i.e. field with highest ID)
if that field does not have an associated "source" or if that field does not cover
any of the requested SpWs specified in inputs.spw. It then performs the same check
as above w.r.t. whether nr. of unique field names is same as nr. of field IDs.
If so, it returns fields by name, otherwise by field ID.

### Intent-to-field pattern 6:

For some PL tasks, the top-level "intent" parameter may contain multiple intents
that are each to be treated separately within the task. In these cases, the task
often employs either if statements or for loops to go through different paths for
each intent, and within those if/for blocks, there are typically separate local
definitions for identifying which fields belong to current given intent.

Examples are found in hifa_gfluxscaleflag, hifa_spwphaseup, and hifa_timegaincal,
that use e.g.:

        for field in inputs.ms.get_fields(intent=intent): 

or some variation, and subsequently may use field.name inside the loop.
This approach bypasses the sanity check (seen in above-mentioned approaches)
of whether a field name is unique for that intent.

As an aside: these tasks usually do still support a top-level "intent" and
"field" input parameter (that might even employ one of the above-mentioned common
patterns), but in practice, they do not really use these input parameters, because
the heuristics are so specifically written for particular intents. I.e. a user
could remove "PHASE" from the inputs.intent in hifa_timegaincal, but that would
effectively undermine the purpose of the task, with likely unexpected outcome in
the task result. In fact, I note in hifa_spwphaseup that the actual intents it
operates on are now hard-coded inside the task, with no way for users to override.


## Future development ideas

* Is there scope to consolidate the 'intent'-to-'field' conversion into fewer variations?
* Consider renaming "field" parameter in Pipeline tasks to "hm_field" and
"intent" to "hm_intent", to distinguish clearly from CASA.
* Enforce type of parameters? E.g. field=1 means field ID 1, while field='1'
means field name "1".
* Consider converting field.name during setter instead of getter.
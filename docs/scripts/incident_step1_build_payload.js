(function execute(inputs, outputs) {
    'use strict';

    var LOG = 'EDA SendIncident/buildPayload: ';

    // event_type is a contract with the rulebooks. Both team rulebooks test
    // payload.event_type == 'servicenow.incident.created'. Changing this string
    // silently stops every rule from firing.
    var EVENT_TYPE = 'servicenow.incident.created';
    var EVENT_VERSION = '1.0';

    outputs.payload = '';
    outputs.is_valid = false;
    outputs.incident_number = '';
    outputs.error_message = '';

    // Step input names are CASE-SENSITIVE and need not match the action input.
    // This step declares 'Incident_record' (capital I) while the action input is
    // 'incident_record'. Accept either rather than depending on which one you are in.
    var record = inputs.incident_record || inputs.Incident_record;

    var incidentSysId = (record && typeof record === 'object' && record.getUniqueValue)
        ? record.getUniqueValue()
        : String(record || '');

    if (!incidentSysId) {
        // Name the inputs that actually arrived - this turns a name mismatch or an
        // unmapped pill from a guessing game into a one-line diagnosis.
        var present = [];
        for (var key in inputs) {
            if (inputs.hasOwnProperty(key)) {
                present.push(key + '=' + (inputs[key] ? 'set' : 'empty'));
            }
        }
        outputs.error_message = 'No incident record supplied. Step inputs present: ' +
            (present.length ? present.join(', ') : '(none)');
        gs.error(LOG + outputs.error_message);
        throw new Error(outputs.error_message);
    }

    var incident = new GlideRecord('incident');
    if (!incident.get(incidentSysId)) {
        outputs.error_message = 'Incident not found: ' + incidentSysId;
        gs.error(LOG + outputs.error_message);
        throw new Error(outputs.error_message);
    }

    outputs.incident_number = incident.getValue('number');

    function cleanFieldValue(value) {
        if (!value) {
            return '';
        }
        return String(value)
            .replace(/<[^>]*>/g, ' ')        // HTML tags
            .replace(/\r\n/g, ' ')
            .replace(/[\n\r\t]/g, ' ')
            .replace(/[\x00-\x1F\x7F]/g, '') // control characters
            .replace(/\\/g, '/')
            .replace(/\s+/g, ' ')
            .trim();
    }

    function displayValue(field) {
        return cleanFieldValue(field ? field.getDisplayValue() : '');
    }

    function rawValue(field) {
        return cleanFieldValue(field ? field.getValue() : '');
    }

    // Instance identity is configuration, not a literal.
    var sourceId = gs.getProperty('x_661661_james_tes.eda.source_id', '');
    if (!sourceId) {
        sourceId = gs.getProperty('instance_name', 'unknown');
    }

    var emAlert = null;
    var originTable = rawValue(incident.origin_table);
    var originId = rawValue(incident.origin_id);

    if (originTable === 'em_alert' && originId) {
        var alertRecord = new GlideRecord('em_alert');
        if (alertRecord.get(originId)) {
            emAlert = alertRecord;
        } else {
            gs.warn(LOG + 'origin is em_alert but alert not found: ' + originId);
        }
    }

    var payload = {
        event_type: EVENT_TYPE,
        event_version: EVENT_VERSION,
        source: sourceId,
        target_team: cleanFieldValue(inputs.team_code),

        incident_number: displayValue(incident.number),
        sys_id: rawValue(incident.sys_id),
        caller: displayValue(incident.caller_id),
        requester: displayValue(incident.u_requester),
        contact_type: displayValue(incident.contact_type),
        short_description: displayValue(incident.short_description),
        description: displayValue(incident.description),

        // Display values keep the original behaviour ("3 - Moderate", "In Progress").
        // The *_value pairs carry raw codes ("3", "2") for numeric comparison.
        priority: displayValue(incident.priority),
        priority_value: rawValue(incident.priority),
        state: displayValue(incident.state),
        state_value: rawValue(incident.state),
        urgency: displayValue(incident.urgency),
        impact: displayValue(incident.impact),

        cmdb_ci: displayValue(incident.cmdb_ci),
        business_service: displayValue(incident.business_service),
        service_offering: displayValue(incident.service_offering),
        application_service: displayValue(incident.u_application_service),
        assigned_to: displayValue(incident.assigned_to),
        assignment_group: displayValue(incident.assignment_group),
        category: displayValue(incident.category),
        origin_table: originTable,
        origin_id: originId,
        root_cause: displayValue(incident.u_root_cause),
        event_issue: displayValue(incident.u_event_issue),
        event_id: displayValue(incident.u_event_id),

        em_alert_node: emAlert ? displayValue(emAlert.node) : '',
        em_metric_name: emAlert ? displayValue(emAlert.metric_name) : '',
        em_resource: emAlert ? displayValue(emAlert.resource) : '',
        em_type: emAlert ? displayValue(emAlert.type) : ''
    };

    outputs.payload = JSON.stringify(payload);
    outputs.is_valid = true;

})(inputs, outputs);

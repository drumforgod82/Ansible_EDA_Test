(function execute(inputs, outputs) {
    'use strict';

    var LOG = 'EDA SendSCTASK/buildPayload: ';

    // Contract with the team rulebooks: they test
    // payload.event_type == 'servicenow.sctask.created'. Change this string and
    // every rule silently stops firing while the stream counter still moves.
    var EVENT_TYPE = 'servicenow.sctask.created';
    var EVENT_VERSION = '1.0';

    outputs.payload = '';
    outputs.is_valid = false;
    outputs.sctask_number = '';
    outputs.error_message = '';

    // Step input names are CASE-SENSITIVE and are declared separately from the
    // pill that feeds them. Accept both spellings so a rename cannot break this.
    var record = inputs.catalog_task_record || inputs.Catalog_task_record;

    // The step input is typed String, so a Reference pill arrives as a sys_id.
    // Handle a real GlideRecord too, in case the step type ever changes.
    var taskSysId = (record && typeof record === 'object' && record.getUniqueValue)
        ? record.getUniqueValue()
        : String(record || '');

    if (!taskSysId) {
        // Name the inputs that actually arrived - this turns a name mismatch or an
        // unmapped pill from a guessing game into a one-line diagnosis.
        var present = [];
        for (var key in inputs) {
            if (inputs.hasOwnProperty(key)) {
                present.push(key + '=' + (inputs[key] ? 'set' : 'empty'));
            }
        }
        outputs.error_message = 'No catalog task supplied. Step inputs present: ' +
            (present.length ? present.join(', ') : '(none)');
        gs.error(LOG + outputs.error_message);
        throw new Error(outputs.error_message);
    }

    var task = new GlideRecord('sc_task');
    if (!task.get(taskSysId)) {
        outputs.error_message = 'Catalog task not found: ' + taskSysId;
        gs.error(LOG + outputs.error_message);
        throw new Error(outputs.error_message);
    }

    outputs.sctask_number = task.getValue('number');

    function cleanFieldValue(value) {
        if (!value) {
            return '';
        }
        return String(value)
            .replace(/<[^>]*>/g, ' ')        // HTML tags
            .replace(/\\n/g, ' ')            // literal backslash-n from catalog variables
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

    // The RITM carries the catalog item, the order guide and the variables.
    var ritm = null;
    var ritmSysId = task.getValue('request_item');
    if (ritmSysId) {
        var ritmGr = new GlideRecord('sc_req_item');
        if (ritmGr.get(ritmSysId)) {
            ritm = ritmGr;
        }
    }

    if (!ritm) {
        outputs.error_message = 'No requested item on ' + outputs.sctask_number +
            ' - cannot resolve the catalog item.';
        gs.error(LOG + outputs.error_message);
        throw new Error(outputs.error_message);
    }

    var payload = {};

    // Catalog variables first, so the reserved keys below always win. There is no
    // GlobalWorkflowHelper on this instance, so read the variable pool directly.
    var mtom = new GlideRecord('sc_item_option_mtom');
    mtom.addQuery('request_item', ritm.getUniqueValue());
    mtom.query();
    while (mtom.next()) {
        var varName = mtom.sc_item_option.item_option_new.name.toString();
        if (varName) {
            payload[varName] = cleanFieldValue(mtom.sc_item_option.value.toString());
        }
    }

    // Instance identity is configuration, not a literal.
    var sourceId = gs.getProperty('x_661661_james_tes.eda.source_id', '');
    if (!sourceId) {
        sourceId = gs.getProperty('instance_name', 'unknown');
    }

    // Reserved routing keys. Set after the variable loop so a catalog variable
    // called event_type or sys_id cannot overwrite them.
    payload.event_type = EVENT_TYPE;
    payload.event_version = EVENT_VERSION;
    payload.source = sourceId;
    payload.target_team = cleanFieldValue(inputs.team_code);

    // These names are the contract with the rulebook's extra_vars mapping.
    payload.task_number = displayValue(task.number);
    payload.sys_id = rawValue(task.sys_id);
    payload.short_description = displayValue(task.short_description);
    payload.assignment_group = displayValue(task.assignment_group);
    payload.catalog_item = displayValue(ritm.cat_item);

    // Extra context, carried for audit and for the playbook's debug output.
    payload.assigned_to = displayValue(task.assigned_to);
    payload.state = displayValue(task.state);
    payload.order_guide = displayValue(ritm.order_guide);
    payload.ritm_number = displayValue(ritm.number);
    payload.ritm_sys_id = rawValue(ritm.sys_id);
    payload.requested_for = '';
    if (!ritm.request.nil()) {
        payload.requested_for = displayValue(ritm.request.requested_for);
    }

    outputs.payload = JSON.stringify(payload);
    outputs.is_valid = true;

})(inputs, outputs);

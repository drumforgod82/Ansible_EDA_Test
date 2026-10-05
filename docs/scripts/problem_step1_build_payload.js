(function execute(inputs, outputs) {
    'use strict';

    var LOG = 'EDA SendProblem/buildPayload: ';

    // Contract with the team rulebooks: they test
    // payload.event_type == 'servicenow.problem.created'. Change this string and
    // every rule silently stops firing while the stream counter still moves.
    var EVENT_TYPE = 'servicenow.problem.created';
    var EVENT_VERSION = '1.0';

    outputs.payload = '';
    outputs.is_valid = false;
    outputs.problem_number = '';
    outputs.error_message = '';

    // Step input names are CASE-SENSITIVE and are declared separately from the
    // pill that feeds them. Accept both spellings so a rename cannot break this.
    var record = inputs.problem_record || inputs.Problem_record;

    // The step input is typed String, so a Reference pill arrives as a sys_id.
    // Handle a real GlideRecord too, in case the step type ever changes.
    var problemSysId = (record && typeof record === 'object' && record.getUniqueValue)
        ? record.getUniqueValue()
        : String(record || '');

    if (!problemSysId) {
        // Name the inputs that actually arrived - this turns a name mismatch or an
        // unmapped pill from a guessing game into a one-line diagnosis.
        var present = [];
        for (var key in inputs) {
            if (inputs.hasOwnProperty(key)) {
                present.push(key + '=' + (inputs[key] ? 'set' : 'empty'));
            }
        }
        outputs.error_message = 'No problem record supplied. Step inputs present: ' +
            (present.length ? present.join(', ') : '(none)');
        gs.error(LOG + outputs.error_message);
        throw new Error(outputs.error_message);
    }

    var problem = new GlideRecord('problem');
    if (!problem.get(problemSysId)) {
        outputs.error_message = 'Problem not found: ' + problemSysId;
        gs.error(LOG + outputs.error_message);
        throw new Error(outputs.error_message);
    }

    outputs.problem_number = problem.getValue('number');

    function cleanFieldValue(value) {
        if (!value) {
            return '';
        }
        return String(value)
            .replace(/<[^>]*>/g, ' ')        // HTML tags - workaround/cause_notes/fix_notes are html
            .replace(/&nbsp;/gi, ' ')        // entity the tag strip leaves behind
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

    // Problem carries booleans that incident does not. Emit real JSON booleans so the
    // rulebook does not have to interpret "0"/"1" or "Yes"/"No".
    function boolValue(field) {
        return field ? field.toString() === 'true' || field.toString() === '1' : false;
    }

    // Instance identity is configuration, not a literal. The scoped property does not
    // exist on this PDI, so this falls through to instance_name - same as the other two actions.
    var sourceId = gs.getProperty('x_661661_james_tes.eda.source_id', '');
    if (!sourceId) {
        sourceId = gs.getProperty('instance_name', 'unknown');
    }

    var payload = {
        // Reserved routing keys. event_type is the rulebook contract; the other three are
        // mapped into extra_vars for audit. Omitting target_team is the failure that looks
        // like success - the job launches with an empty team.
        event_type: EVENT_TYPE,
        event_version: EVENT_VERSION,
        source: sourceId,
        target_team: cleanFieldValue(inputs.team_code),

        // The five keys the Problem rule maps into extra_vars.
        problem_number: displayValue(problem.number),
        short_description: displayValue(problem.short_description),
        assignment_group: displayValue(problem.assignment_group),
        cmdb_ci: displayValue(problem.cmdb_ci),
        sys_id: problem.getUniqueValue(),

        // Extra context: carried for audit and the playbook's debug output.
        // Display values read like the UI; the *_value pairs carry raw codes, which is
        // what the Table API wants back. Problem state is 101-107, NOT incident's 1-8.
        state: displayValue(problem.state),
        state_value: rawValue(problem.state),
        priority: displayValue(problem.priority),
        priority_value: rawValue(problem.priority),
        urgency: displayValue(problem.urgency),
        impact: displayValue(problem.impact),

        description: displayValue(problem.description),
        category: displayValue(problem.category),
        subcategory: displayValue(problem.subcategory),
        assigned_to: displayValue(problem.assigned_to),
        opened_at: displayValue(problem.opened_at),
        opened_by: displayValue(problem.opened_by),
        contact_type: displayValue(problem.contact_type),
        business_service: displayValue(problem.business_service),
        service_offering: displayValue(problem.service_offering),

        // first_reported_by_task is a reference to a TASK, not a user - its display value
        // is the originating ticket number. Named honestly rather than as "reported_by".
        first_reported_by_task: displayValue(problem.first_reported_by_task),
        duplicate_of: displayValue(problem.duplicate_of),
        rfc: displayValue(problem.rfc),
        related_incidents: rawValue(problem.related_incidents),

        // Empty at creation; populated by the playbook when it resolves with fix_applied,
        // which requires both. Sent so a re-run can see what a previous run wrote.
        cause_notes: displayValue(problem.cause_notes),
        fix_notes: displayValue(problem.fix_notes),
        workaround: displayValue(problem.workaround),
        resolution_code: displayValue(problem.resolution_code),
        known_error_article: displayValue(problem.primary_known_error_article),

        major_problem: boolValue(problem.major_problem),
        known_error: boolValue(problem.known_error)
    };

    // NOT PORTED FROM cncdev - these columns do not exist on this instance (verified against
    // sys_dictionary for problem + task, 2026-10-02). Add them back when this action is built
    // on cncdev, where they are Centene customisations:
    //   u_requester, u_application_service, u_root_cause, u_type, u_risk_of_reoccurence,
    //   u_technology_owner_group, u_business_impact_html, u_caused_by, u_cause_category, u_repeat_of
    // cncdev also aliases `category` as "symptom" on the Problem form; the column is still category.

    outputs.payload = JSON.stringify(payload);
    outputs.is_valid = true;

})(inputs, outputs);

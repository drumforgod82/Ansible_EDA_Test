(function execute(inputs, outputs) {
    'use strict';

    var LOG = 'EDA SendIncident/handleResponse: ';
    var BODY_IN_OUTPUT = 500;
    var BODY_IN_ERROR = 200;

    outputs.success = false;
    outputs.http_status = '';
    outputs.response_body = '';
    outputs.error_message = '';

    // Input names must match the step declared variable names exactly.
    // A mismatch reads as undefined with no error.
    var status = String(inputs.status_code || '');
    var body = String(inputs.response_body || '');
    var restError = String(inputs.rest_error_message || '');

    outputs.http_status = status;
    outputs.response_body = body.substring(0, BODY_IN_OUTPUT);

    // 202 counts as success. The event stream may acknowledge asynchronously.
    if (status === '200' || status === '201' || status === '202') {
        outputs.success = true;
        return;
    }

    // An empty status means the request never left the instance: a connection,
    // alias, or credential problem rather than an endpoint rejection.
    if (status === '') {
        if (restError) {
            outputs.error_message = 'Request not sent: ' + restError.substring(0, BODY_IN_ERROR);
        } else {
            outputs.error_message = 'Request not sent and the REST step reported no error.';
        }
    } else {
        outputs.error_message = 'HTTP ' + status + ': ' + body.substring(0, BODY_IN_ERROR);
    }

    gs.error(LOG + outputs.error_message);

})(inputs, outputs);

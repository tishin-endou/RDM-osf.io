'use strict';

var $ = require('jquery');
var nodeApiUrl = window.contextVars.node.urls.api;
var timestampCommon = require('./timestamp-common.js');
timestampCommon.setWebOrAdmin('web');

var $osf = require('../osfHelpers');
var moment = require('moment');

function datesToLocal() {
    var cells = document.querySelectorAll('td[class=verify_date]');
    for (var i = 0; i < cells.length; i++) {
        var cell = cells[i];
        var newDateText;
        if (cell.textContent === 'Unknown') {
            newDateText = cell.textContent;
        }
        else {
            newDateText = new $osf.FormattableDate(new Date(cell.textContent)).local;
        }
        cell.textContent = newDateText;
        cell.style.color = 'inherit';
    }
}

$(document).ready(function () {
    timestampCommon.init(window.contextVars.node.urls.api + 'timestamp/task_status/');
    datesToLocal();
});

$(function () {
    $('#btn-verify').on('click', function () {
        if ($('#btn-verify').attr('disabled') !== undefined || $('#btn-addtimestamp').attr('disabled') !== undefined) {
            return false;
        }
        timestampCommon.verify({
            urlVerify: 'json/',
            urlVerifyData: nodeApiUrl + 'timestamp/timestamp_error_data/',
            method: 'GET'
        });
    });

    $('#btn-addtimestamp').on('click', function () {
        if ($('#btn-verify').attr('disabled') !== undefined || $('#btn-addtimestamp').attr('disabled') !== undefined) {
            return false;
        }
        timestampCommon.add({
            url: nodeApiUrl + 'timestamp/add_timestamp/',
            method: 'POST'
        });
    });

    $('#btn-cancel').on('click', function () {
        if ($('#btn-cancel').attr('disabled') !== undefined) {
            return false;
        }
        timestampCommon.cancel(nodeApiUrl + 'timestamp/cancel_task/');
    });

    $('#btn-download').on('click', function () {
        timestampCommon.download();
    });

    $('#timestamp_errors_spinner').hide();
});

/**
* Controller for the Add Contributor modal.
*/
var $ = require('jquery');
var ko = require('knockout');
var $osf = require('osfHelpers');
var bootbox = require('bootbox');
var Paginator = require('./paginator');

require('bootstrap-editable');
var oop = require('js/oop');

var NODE_OFFSET = 25;
// Max number of recent/common contributors to show
var MAX_RECENT = 5;

function Contributor(data) {
    $.extend(this, data);
    if (data.n_projects_in_common === 1) {
        this.displayProjectsInCommon = data.n_projects_in_common + ' project in common';
    } else if (data.n_projects_in_common !== 0) {
        this.displayProjectsInCommon = data.n_projects_in_common + ' projects in common';
    } else {
        this.displayProjectsInCommon = '';
    }
}

var AddContributorViewModel = oop.extend (Paginator, {
    constructor(title, parentId, parentTitle) {
        this.super.constructor();
        var self = this;

        self.permissions = ['read', 'write', 'admin'];

        self.title = title;
        self.parentId = parentId;
        self.parentTitle = parentTitle;

        self.page = ko.observable('whom');
        self.pageTitle = ko.computed(function() {
            return {
                whom: 'Add Contributors',
                which: 'Select Components',
                invite: 'Add Unregistered Contributor'
            }[self.page()];
        });
        self.query = ko.observable();
        self.results = ko.observableArray([]);
        self.selection = ko.observableArray();
        self.notification = ko.observable('');
        self.inviteError = ko.observable('');
        self.totalPages = ko.observable(0);
        self.nodes = ko.observableArray([]);
        self.nodesToChange = ko.observableArray();
        $.getJSON(
            nodeApiUrl + 'get_editable_children/',
            {},
            function(result) {
                $.each(result.children || [], function(idx, child) {
                    child.margin = NODE_OFFSET + child.indent * NODE_OFFSET + 'px';
                });
                self.nodes(result.children);
            }
        );
        self.foundResults = ko.computed(function() {
            return self.query() && self.results().length;
        });

        self.noResults = ko.computed(function() {
            return self.query() && !self.results().length;
        });

        self.inviteName = ko.observable();
        self.inviteEmail = ko.observable();

        self.addingSummary = ko.computed(function() {
            var names = $.map(self.selection(), function(result) {
                return result.fullname;
        });
        return names.join(', ');
    });
    },
    selectWhom() {
        this.page('whom');
    },
    selectWhich() {
        this.page('which');
    },
    gotoInvite() {
        var self = this;
        self.inviteName(self.query());
        self.inviteError('');
        self.inviteEmail('');
        self.page('invite');
    },
    goToPage (page) {
        this.page(page);
    },
    /**
        * A simple Contributor model that receives data from the
        * contributor search endpoint. Adds an addiitonal displayProjectsinCommon
        * attribute which is the human-readable display of the number of projects the
        * currently logged-in user has in common with the contributor.
        */
    startSearch() {
        this.currentPage(0);
        this.search();
    },
    search() {
        var self = this;
        self.notification(false);
        if (self.query()) {
            $.getJSON(
                '/api/v1/user/search/',
                {
                    query: self.query(),
                    excludeNode: nodeId,
                    page: self.currentPage
                },
                function(result) {
                    var contributors = result.users.map(function(userData) {
                        return new Contributor(userData);
                    });
                    self.results(contributors);
                    self.currentPage(result.page);
                    self.numberOfPages(result.pages);
                    self.addNewPaginators();
                }
            );
        } else {
            self.results([]);
            self.currentPage(0);
            self.totalPages(0);
        }
    },
    importFromParent() {
        self.notification(false);
        $.getJSON(
            nodeApiUrl + 'get_contributors_from_parent/',
            {},
            function(result) {
                if (!result.contributors.length) {
                    self.notification({
                        'message': 'All contributors from parent already included.',
                        'level': 'info'
                    });
                }
                self.results(result.contributors);
            }
        );
    },
    recentlyAdded() {
        var self = this;
        self.notification(false);
        var url = nodeApiUrl + 'get_recently_added_contributors/?max=' + MAX_RECENT.toString();
        $.getJSON(
            url,
            {},
            function(result) {
                if (!result.contributors.length) {
                    self.notification({
                        'message': 'All recent collaborators already included.',
                        'level': 'info'
                    });
                }
                var contribs = [];
                var numToDisplay = result.contributors.length;
                for (var i=0; i< numToDisplay; i++) {
                    contribs.push(new Contributor(result.contributors[i]));
                }
                self.results(contribs);
                self.numberOfPages(1);
            }
        ).fail(function (xhr, textStatus, error) {
            self.notification({
                'message':
                    'OSF was unable to resolve your request. If this issue persists, ' +
                    'please report it to <a href="mailto:support@osf.io">support@osf.io</a>.',
                'level': 'warning'
            });
            Raven.captureMessage('Could not GET recentlyAdded contributors.', {
                url: url,
                textStatus: textStatus,
                error: error
            });
        });
    },
    mostInCommon() {
        var self = this;
        self.notification(false);
        var url = nodeApiUrl + 'get_most_in_common_contributors/?max=' + MAX_RECENT.toString();
        $.getJSON(
            url,
            {},
            function(result) {
                if (!result.contributors.length) {
                    self.notification({
                        'message': 'All frequent collaborators already included.',
                        'level': 'info'
                    });
                }
                var contribs = [];
                var numToDisplay = result.contributors.length;
                for (var i=0; i< numToDisplay; i++) {
                    contribs.push(new Contributor(result.contributors[i]));
                }
                self.results(contribs);
                self.numberOfPages(1);
            }
        ).fail(function (xhr, textStatus, error) {
            self.notification({
                'message':
                    'OSF was unable to resolve your request. If this issue persists, ' +
                    'please report it to <a href="mailto:support@osf.io">support@osf.io</a>.',
                'level': 'warning'
            });
            Raven.captureMessage('Could not GET mostInCommon contributors.', {
                url: url,
                textStatus: textStatus,
                error: error
            });
        });
    },
    addTips(elements) {
        elements.forEach(function(element) {
            $(element).find('.contrib-button').tooltip();
        });
    },
    setupEditable(elm, data) {
        var $elm = $(elm);
        var $editable = $elm.find('.permission-editable');
        $editable.editable({
            showbuttons: false,
            value: 'admin',
            source: [
                {value: 'read', text: 'Read'},
                {value: 'write', text: 'Read + Write'},
                {value: 'admin', text: 'Administrator'}
            ],
            success: function(response, value) {
                data.permission(value);
            }
        });
    },
    afterRender(elm, data) {
        var self = this;
        self.addTips(elm, data);
        self.setupEditable(elm, data);
    },
    makeAfterRender(){
        var self = this;
        return function(elm, data){
            return self.afterRender(elm, data);
        };
    },
    /** Validate the invite form. Returns a string error message or
    *   true if validation succeeds.
    */
    validateInviteForm(){
        var self = this;
        // Make sure Full Name is not blank
        if (!self.inviteName().trim().length) {
            return 'Full Name is required.';
        }
        if (self.inviteEmail() && !$osf.isEmail(self.inviteEmail())) {
            return 'Not a valid email address.';
        }
        // Make sure that entered email is not already in selection
        for (var i=0, contrib; contrib = self.selection()[i]; ++i){
            var contribEmail = contrib.email.toLowerCase().trim();
            if (contribEmail === self.inviteEmail().toLowerCase().trim()) {
                return self.inviteEmail() + ' is already in queue.';
            }
        }
        return true;
    },
    postInvite() {
        var self = this;
        self.inviteError('');
        var validated = self.validateInviteForm();
        if (typeof validated === 'string') {
            self.inviteError(validated);
            return false;
        }
        return self.postInviteRequest(self.inviteName(), self.inviteEmail());
    },
    add(data) {
        data.permission = ko.observable('admin');
        // All manually added contributors are visible
        data.visible = true;
        this.selection.push(data);
        // Hack: Hide and refresh tooltips
        $('.tooltip').hide();
        $('.contrib-button').tooltip();
    },
    remove(data) {
        this.selection.splice(
            this.selection.indexOf(data), 1
        );
        // Hack: Hide and refresh tooltips
        $('.tooltip').hide();
        $('.contrib-button').tooltip();
    },
    addAll() {
        $.each(this.results(), function(idx, result) {
            if (this.selection().indexOf(result) === -1) {
                this.add(result);
            }
        });
    },
    removeAll() {
        $.each(this.selection(), function(idx, selected) {
            this.remove(selected);
        });
    },
    cantSelectNodes() {
        return this.nodesToChange().length === this.nodes().length;
    },
    cantDeselectNodes() {
        return this.nodesToChange().length === 0;
    },
    selectNodes() {
        this.nodesToChange($osf.mapByProperty(this.nodes(), 'id'));
    },
    deselectNodes() {
        this.nodesToChange([]);
    },
    selected(data) {
        for (var idx=0; idx < this.selection().length; idx++) {
            if (data.id === this.selection()[idx].id){
                return true;
            }
        }
        return false;
    },
    submit() {
        var self = this;
        $osf.block();
        $osf.postJSON(
            nodeApiUrl + 'contributors/',
            {
                users: self.selection().map(function(user) {
                    return ko.toJS(user);
                }),
                node_ids: self.nodesToChange()
            }
        ).done(function() {
            window.location.reload();
        }).fail(function() {
            $('.modal').modal('hide');
            $osf.unblock();
            $osf.growl('Error','Add contributor failed.');
        });
    },
    clear() {
        var self = this;
        self.page('whom');
        self.query('');
        self.results([]);
        self.selection([]);
        self.nodesToChange([]);
        self.notification(false);
    },
    postInviteRequest(fullname, email) {
        var self = this;
        $osf.postJSON(
            nodeApiUrl + 'invite_contributor/',
            {'fullname': fullname, 'email': email}
        ).done(
            self.onInviteSuccess.bind(self)
        ).fail(
            self.onInviteError.bind(self)
        );
    },
    onInviteSuccess(result) {
        var self = this;
        self.query('');
        self.results([]);
        self.page('whom');
        self.add(result.contributor);
    },
    onInviteError(xhr) {
        var response = JSON.parse(xhr.responseText);
        // Update error message
        this.inviteError(response.message);
    }
});


////////////////
// Public API //
////////////////

function ContribAdder (selector, nodeTitle, nodeId, parentTitle) {
    var self = this;
    self.selector = selector;
    self.$element = $(selector);
    self.nodeTitle = nodeTitle;
    self.nodeId = nodeId;
    self.parentTitle = parentTitle;
    self.viewModel = new AddContributorViewModel(self.nodeTitle,
        self.nodeId, self.parentTitle);
    self.init();
}

ContribAdder.prototype.init = function() {
    var self = this;
    ko.applyBindings(self.viewModel, self.$element[0]);
    // Clear popovers on dismiss start
    self.$element.on('hide.bs.modal', function() {
        self.$element.find('.popover').popover('hide');
    });
    // Clear user search modal when dismissed; catches dismiss by escape key
    // or cancel button.
    self.$element.on('hidden.bs.modal', function() {
        self.viewModel.clear();
    });
    // Load recently added contributors every time the modal is activated.
    self.$element.on('shown.bs.modal', function() {
        self.viewModel.recentlyAdded();
    });
};

module.exports = ContribAdder;

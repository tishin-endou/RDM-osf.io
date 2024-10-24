
<%inherit file="base.mako"/>

<%def name="title()">${_("Account Settings")}</%def>
<%def name="content()">
    <% from website import settings %>
    <div id="accountSettings">
        <h2 class="page-header">${_("Settings")}</h2>
        <div class="row">
            <div class="col-md-3 affix-parent">
              <%include file="include/profile/settings_navpanel.mako" args="current_page='account'"/>
            </div>
            <div class="col-md-6">
                <div id="connectedEmails" class="panel panel-default scripted">
                    <div class="panel-heading clearfix"><h3 class="panel-title">${_("Connected Emails")}</h3></div>
                    <div class="panel-body">
                        <table class="table">
                            <thead>
                                <tr>
                                    <th colspan="2">${_("Primary Email")}</th>
                                </tr>
                            </thead>
                            <tbody>
                                <tr>
                                    <td><span data-bind="text: profile().primaryEmail().address"></span></td>
                                    <td></td>
                                </tr>
                            </tbody>
                        </table>

                        <table class="table">
                            <thead>
                                <tr>
                                    <th colspan="3">${_("Alternate Emails")}</th>
                                </tr>
                            </thead>
                            <tbody data-bind="foreach: profile().alternateEmails()">
                                <tr>
                                    <td style="word-break: break-all;"><span data-bind="text: $data.address"></span></td>
                                    <td style="width:150px;"><a data-bind="click: $parent.makeEmailPrimary.bind($parent)">${_("make&nbsp;primary") | n}</a></td>
                                    <td style="width:50px;"><a data-bind="click: $parent.removeEmail.bind($parent)"><i class="fa fa-times text-danger"></i></a></td>
                                </tr>
                            </tbody>
                        </table>
                        <table class="table">
                            <thead>
                                <tr>
                                    <th colspan="3">${_("Unconfirmed Emails")}</th>
                                </tr>
                            </thead>
                            <tbody>
                                <!-- ko foreach: profile().unconfirmedEmails() -->
                                <tr>
                                    <td style="word-break: break-all;"><span data-bind="text: $data.address"></span></td>
                                    <td style="width:150px;"><a data-bind="click: $parent.resendConfirmation.bind($parent)">${_("resend&nbsp;confirmation") | n}</a></td>
                                    <td style="width:50px;" ><a data-bind="click: $parent.removeEmail.bind($parent)"><i class="fa fa-times text-danger"></i></a></td>
                                </tr>
                                <!-- /ko -->
                                <tr>
                                    <td colspan="3">
                                        <form data-bind="submit: addEmail">
                                            <p>
                                            % if user_merge:
                                            ${_("To merge an existing account with this one or to log in with multiple email addresses, add an alternate email address below.")}
                                            <span class="fa fa-info-circle" data-bind="tooltip: {title: '${_("Merging accounts will move all projects and components associated with two emails into one account. All projects and components will be displayed under the email address listed as primary.")}',
                                             placement: 'bottom', container : 'body'}"></span>
                                            % else:
                                            ${_("To log in with multiple email addresses, add an alternate email address below.")}
					    % endif
                                            </p>
                                            <div class="form-group">
                                                ## email input verification is not supported on safari
                                              <input placeholder="${_('Email address')}" type="email" data-bind="value: emailInput" class="form-control" required maxlength="254">
                                            </div>
                                            <input type="submit" value="${_('Add email')}" class="btn btn-success">
                                        </form>

                                        <div class="help-block">
                                            <p data-bind="html: message, attr: {class: messageClass}"></p>
                                        </div>
                                    </td>

                                </tr>
                            </tbody>
                        </table>
                    </div>
                </div>
                % if storage_flag_is_active:
                    <div class="panel panel-default">
                        <div class="panel-heading clearfix"><h3 class="panel-title">${_("Default Storage Location")}</h3></div>
                        <div class="panel-body">
                            <form id="updateDefaultStorageLocation" data-bind="submit: $root.updateDefaultStorageLocation.bind($root)" role="form">
                                <div class="form-group">
                                    <select class="form-control" data-bind="options: locations, value: locationSelected, optionsText: function(item) { return item.name }">
                                    </select>
                                    <div class="help-block">
                                        <p>
                                            ${_("This location will be applied to new projects and components. It will not affect existing projects and components.")}
                                        </p>
                                    </div>
                                </div>
                                <p class="text-muted"></p>
                                <button class="btn btn-primary" type="submit">${_("Update location")}</button>
                            </form>
                        </div>
                    </div>
                % endif
                %if use_external_identity:
                <div id="externalIdentity" class="panel panel-default">
                    <div class="panel-heading clearfix"><h3 class="panel-title">${_("Connected Identities")}</h3></div>
                    <div class="panel-body">
                        <p> ${_("Connected identities allow you to log in to the GakuNin RDM via a third-party service.")} <br/>
                        ${_("You can revoke these authorizations here.")}</p>
                        <hr />
                        % if not external_identity:
                        <p >${_("You have not authorized any external services to log in to the GakuNin RDM.")}</p>
                        % endif
                        <tbody>
                        % for identity in external_identity:
                        <div id="externalLogin-${identity}">
                            % for id in external_identity[identity]:
                            <div><tr>
                                <td>
                                    ${identity}: ${id} (
                                    % if external_identity[identity][id] == "VERIFIED":
                                        ${_("Verified")}
                                    % else:
                                        ${_("Pending")}
                                    % endif
                                    )
                                </td>
                                <td>
                                    <a data-bind="click: $root.removeIdentity.bind($root, '${id}')"><i class="fa fa-times text-danger pull-right"></i></a>
                                </td>
                            </tr></div>
                            % if not loop.last:
                            <hr />
                            % endif
                            % endfor
                        </div>
                        % endfor
                        </tbody>
                    </div>
                </div>
                %endif
                %if use_change_password:
                <div id="changePassword" class="panel panel-default">
                    <div class="panel-heading clearfix"><h3 class="panel-title">${_("Change Password")}</h3></div>
                    <div class="panel-body">
                        <form id="changePasswordForm" role="form" action="${ web_url_for('user_account_password') }" method="post">
                            <div class="form-group">
                                <label for="old_password">${_("Old password")}</label>
                                <input
                                    type="password"
                                    class="form-control"
                                    id="changePassword"
                                    placeholder="${_('Old Password')}"
                                    name="old_password"
                                    data-bind="
                                        textInput: oldPassword,
                                        value: oldPassword,
                                        event: {
                                            blur: trim.bind($data, password)
                                        }"
                                >
                                <p class="help-block" data-bind="validationMessage: oldPassword" style="display: none;"></p>
                            </div>
                            <div class="form-group">
                                <label for="new_password">${_("New password")}</label>
                                <input
                                    type="password"
                                    class="form-control"
                                    id="resetPassword"
                                    placeholder="${_('New Password')}"
                                    name="new_password"
                                    data-bind="
                                        textInput: typedPassword,
                                        value: password,
                                        event: {
                                            blur: trim.bind($data, password)
                                        }"
                                >
                                <div class="row" data-bind="visible: typedPassword().length > 0">
                                    <div class="col-xs-8">
                                        <div class="progress create-password">
                                            <div class="progress-bar progress-bar-sm" role="progressbar" data-bind="attr: passwordComplexityInfo().attr"></div>
                                        </div>
                                    </div>
                                    <div class="col-xs-4 f-w-xl">
                                        <!-- ko if: passwordFeedback() -->
                                        <p id="front-password-info" data-bind="text: passwordComplexityInfo().text, attr: passwordComplexityInfo().text_attr"></p>
                                        <!-- /ko -->
                                    </div>
                                </div>

                                <div>
                                    <!-- ko if: passwordFeedback() -->
                                    <p class="help-block osf-box-lt p-xs" data-bind="validationMessage: password" style="display: none;"></p>
                                    <p class="osf-box-lt " data-bind="css : { 'p-xs': passwordFeedback().warning }, visible: typedPassword().length > 0, text: passwordFeedback().warning"></p>
                                    <!-- /ko -->
                                </div>
                            </div>
                            <div class="form-group">
                                <label for="confirm_password">${_("Confirm new password")}</label>
                                <input
                                    type="password"
                                    class="form-control"
                                    id="resetPasswordConfirmation"
                                    placeholder="${_('Verify Password')}"
                                    name="confirm_password"
                                    data-bind="
                                        value: passwordConfirmation,
                                        event: {
                                            blur: trim.bind($data, passwordConfirmation)
                                        }"
                                >
                                <p class="help-block" data-bind="validationMessage: passwordConfirmation" style="display: none;"></p>
                            </div>
                            ## TODO: [#OSF-6764] change so that password strength submit validation happens in knockout on the form, not with this disable
                            <button type="submit" class="btn btn-primary" data-bind="disable: !password.isValid()">${_("Update password")}</button>
                        </form>
                    </div>
                </div>
                %endif
                %if use_tfa:
                <div class="panel panel-default">
                  <div class="panel-heading clearfix"><h3 class="panel-title">${_("Security Settings")}</h3></div>
                  <div class="panel-body">
                    % for addon in addons:
                    ${render_user_settings(addon) }
                    % if not loop.last:
                    <hr />
                    % endif
                    % endfor
                  </div>
                </div>
                %endif
                <div id="exportAccount" class="panel panel-default">
                    <div class="panel-heading clearfix"><h3 class="panel-title">${_("Export Account Data")}</h3></div>
                    <div class="panel-body">
                        <p>${_("Exporting your account data allows you to keep a permanent copy of the current state of your account. Keeping a copy of your account data can provide peace of mind or assist in transferring your information to another provider.")}</p>
                        <a class="btn btn-primary" data-bind="click: submit, css: success() === true ? 'disabled' : ''">${_("Request export")}</a>
                    </div>
                </div>
                <div id="deactivateAccount" class="panel panel-default">
                    <div class="panel-heading clearfix"><h3 class="panel-title">${_("Deactivate Account")}</h3></div>
                    <div class="panel-body">
                        <p class="alert alert-warning">${_("<strong>Warning:</strong> Once your deactivation has been approved the effects are irreversible.") | n}</p>
                        <p>${_("Deactivating your account will remove you from all public projects to which you are a contributor. Your account will no longer be associated with GakuNin RDM projects, and your work on the GakuNin RDM will be inaccessible.")}</p>
                        <p data-bind="click: cancel, visible: requestPending()"><b>${_("Your account is currently pending deactivation.")}</b></p>
                        <a class="btn btn-danger" data-bind="click: submit, visible: !requestPending()">${_("Request deactivation")}</a>
                        <a class="btn btn-success" data-bind="click: cancel, visible: requestPending()">${_("Cancel deactivation request")}</a>
                    </div>
                </div>
            </div>
        </div>
    </div>
    <script src=${"/static/public/js/profile-account-settings-page.js" | webpack_asset}></script>
</%def>

<%def name="stylesheets()">
  ${parent.stylesheets()}
  % for stylesheet in addons_css:
      <link rel="stylesheet" type="text/css" href="${stylesheet}">
  % endfor
</%def>

<%def name="render_user_settings(config)">
    <%
       template = config['user_settings_template']
       tpl = template.render(**config)
    %>
    ${ tpl | n }
</%def>

<%def name="javascript_bottom()">
    <script type="text/javascript">
        window.contextVars = $.extend(true, {}, window.contextVars, {
            username: ${user_name | sjson, n},
            requestedDeactivation: ${requested_deactivation | sjson, n}
        });
    </script>
    ${parent.javascript_bottom()}
    ## Webpack bundles
    % for js_asset in addons_js:
      <script src="${js_asset | webpack_asset}"></script>
    % endfor
</%def>

(function () {
  'use strict';

angular.module('CyBorgBackup.utils', [])
.filter('sanitize', function() {
     return function(input) {
         input = $("<span>").text(input)[0].innerHTML;
         return input;
     };
 })

.factory('Empty', [
    function() {
        return function(val) {
            return (val === null || val === undefined || val === '') ? true : false;
        };
    }
])

.factory('Store', ['Empty',
    function(Empty) {
        return function(key, value) {
            if (!Empty(value)) {
                // Store the value
                localStorage[key] = JSON.stringify(value);
            } else if (!Empty(key)) {
                // Return the value
                var val = localStorage[key];
                return (!Empty(val)) ? JSON.parse(val) : null;
            }
        };
    }
])

.factory('Wait', ['$rootScope',
    function($rootScope) {

        return function(directive) {
            var docw, doch, spinnyw, spinnyh;
            if (directive === 'start' && !$rootScope.waiting) {
                $rootScope.waiting = true;
                docw = $(window).width();
                doch = $(window).height();
                spinnyw = $('.spinny').width();
                spinnyh = $('.spinny').height();
                $('.overlay').css({
                    width: $(document).width(),
                    height: $(document).height()
                }).fadeIn();
                $('.spinny').css({
                    bottom: 15,
                    right: 15
                }).fadeIn(400);
            } else if (directive === 'stop' && $rootScope.waiting) {
                $('.spinny, .overlay').fadeOut(400, function() {
                    $rootScope.waiting = false;
                });
            }
        };
    }
])

.factory('Alert', ['$rootScope', '$filter', function($rootScope, $filter) {
    return function(hdr, msg, cls, action, secondAlert, disableButtons, backdrop, customStyle) {
        var scope = $rootScope.$new(),
            alertClass, local_backdrop;
        if (customStyle !== true) {
            msg = $filter('sanitize')(msg);
        }
        if (secondAlert) {

            $('#alertHeader2').html(hdr);
            $('#alert2-modal-msg').html(msg);

            alertClass = (cls) ? cls : 'alert-danger'; //default alert class is alert-danger
            local_backdrop = (backdrop === undefined) ? "static" : backdrop;

            $('#alert2-modal-msg').attr({ "class": "alert " + alertClass });
            $('#alert-modal2').modal({
                show: true,
                keyboard: true,
                backdrop: local_backdrop
            });
            scope.disableButtons2 = (disableButtons) ? true : false;

            $('#alert-modal2').on('hidden.bs.modal', function() {
                if (action) {
                    action();
                }
            });
            $('#alert-modal2').on('shown.bs.modal', function() {
                $('#alert2_ok_btn').focus();
            });
            $(document).bind('keydown', function(e) {
                if (e.keyCode === 27 || e.keyCode === 13) {
                    e.preventDefault();
                    $('#alert-modal2').modal('hide');
                }
            });
        } else {

            $('#alertHeader').html(hdr);
            $('#alert-modal-msg').html(msg);
            alertClass = (cls) ? cls : 'alert-danger'; //default alert class is alert-danger
            local_backdrop = (backdrop === undefined) ? "static" : backdrop;

            $('#alert-modal-msg').attr({ "class": "alert " + alertClass });
            $('#alert-modal').modal({
                show: true,
                keyboard: true,
                backdrop: local_backdrop
            });

            $('#alert-modal').on('hidden.bs.modal', function() {
                if (action) {
                    action();
                }
                $('.modal-backdrop').remove();
            });
            $('#alert-modal').on('shown.bs.modal', function() {
                $('#alert_ok_btn').focus();
            });
            $(document).bind('keydown', function(e) {
                if (e.keyCode === 27 || e.keyCode === 13) {
                    e.preventDefault();
                    $('#alert-modal').modal('hide');
                }
            });

            scope.disableButtons = (disableButtons) ? true : false;
        }
    };
}])

.factory('ProcessErrors', ['$rootScope', '$cookies', '$log', '$location', 'Alert', 'Wait',
    function($rootScope, $cookies, $log, $location, Alert, Wait) {
        return function(scope, data, status, form, defaultMsg) {
            var field, fieldErrors, msg, keys;
            Wait('stop');
            $log.debug('Debug status: ' + status);
            $log.debug('Debug data: ');
            $log.debug(data);
            if (defaultMsg.msg) {
                $log.debug('Debug: ' + defaultMsg.msg);
            }
            if (status === 403) {
                if (data && data.detail) {
                    msg = data.detail;
                } else {
                    msg = 'The API responded with a 403 Access Denied error. Please contact your system administrator.';
                }
                Alert(defaultMsg.hdr, msg);
            } else if (status === 409) {
                Alert('Conflict', data.conflict || "Resource currently in use.");
            } else if (status === 410) {
                Alert('Deleted Object', 'The requested object was previously deleted and can no longer be accessed.');
            } else if ((status === 'Session is expired') || (status === 401 && data.detail && data.detail === 'Token is expired') ||
                (status === 401 && data && data.detail && data.detail === 'Invalid token')) {
                if ($rootScope.sessionTimer) {
                    $rootScope.sessionTimer.expireSession('idle');
                }
                $location.url('/login');
            } else if (data && data.non_field_errors) {
                Alert('Error!', data.non_field_errors);
            } else if (data && data.detail) {
                Alert(defaultMsg.hdr, defaultMsg.msg + ' ' + data.detail);
            } else if (data && data.__all__) {
                if (typeof data.__all__ === 'object' && Array.isArray(data.__all__)) {
                    Alert('Error!', data.__all__[0]);
                } else {
                    Alert('Error!', data.__all__);
                }
            } else if (form) { //if no error code is detected it begins to loop through to see where the api threw an error
                fieldErrors = false;
                for (field in form.fields) {
                    if (data[field] && form.fields[field].tab) {
                        // If the form is part of a tab group, activate the tab
                        $('#' + form.name + "_tabs a[href=\"#" + form.fields[field].tab + '"]').tab('show');
                    }
                    if (form.fields[field].realName) {
                        if (data[form.fields[field].realName]) {
                            scope[field + '_api_error'] = data[form.fields[field].realName][0];
                            //scope[form.name + '_form'][form.fields[field].realName].$setValidity('apiError', false);
                            $('[name="' + form.fields[field].realName + '"]').addClass('ng-invalid');
                            $('html, body').animate({scrollTop: $('[name="' + form.fields[field].realName + '"]').offset().top}, 0);
                            fieldErrors = true;
                        }
                    }
                    if (form.fields[field].sourceModel) {
                        if (data[field]) {
                            scope[form.fields[field].sourceModel + '_' + form.fields[field].sourceField + '_api_error'] =
                                data[field][0];
                            //scope[form.name + '_form'][form.fields[field].sourceModel + '_' + form.fields[field].sourceField].$setValidity('apiError', false);
                            $('[name="' + form.fields[field].sourceModel + '_' + form.fields[field].sourceField + '"]').addClass('ng-invalid');
                            $('[name="' + form.fields[field].sourceModel + '_' + form.fields[field].sourceField + '"]').ScrollTo({ "onlyIfOutside": true, "offsetTop": 100 });
                            fieldErrors = true;
                        }
                    } else {
                        if (data[field]) {
                            scope[field + '_api_error'] = data[field][0];
                            //scope[form.name + '_form'][field].$setValidity('apiError', false);
                            $('[name="' + field + '"]').addClass('ng-invalid');
                            $('html, body').animate({scrollTop: $('[name="' + field + '"]').offset().top}, 0);
                            fieldErrors = true;
                        }
                    }
                }
                if ((!fieldErrors) && defaultMsg) {
                    Alert(defaultMsg.hdr, defaultMsg.msg);
                }
            } else if (typeof data === 'object' && data !== null) {
                if (Object.keys(data).length > 0) {
                    keys = Object.keys(data);
                    if (Array.isArray(data[keys[0]])) {
                        msg = data[keys[0]][0];
                    } else {
                        msg = "";
                        _.forOwn(data, function(value, key) {
                            msg += '${key} : ${value} ';
                        });
                    }
                    Alert(defaultMsg.hdr, msg);
                } else {
                    Alert(defaultMsg.hdr, defaultMsg.msg);
                }
            } else {
                Alert(defaultMsg.hdr, defaultMsg.msg);
            }
        };
    }
])

.factory('LoadBasePaths', ['$http', '$rootScope', 'Store', 'ProcessErrors',
    function ($http, $rootScope, Store, ProcessErrors) {
        return function () {

            $http({ method: 'GET', url:'/api/', headers: { 'Authorization': "" } })
                .then(function({data}){
                    var base = data.current_version;
                    $http({ method: 'GET', url:base, headers: { 'Authorization': "" } })
                        .then(function({data}){
                            data.base = base;
                            $rootScope.defaultUrls = data;
                            Store('api', data);
                        })
                        .catch(function(data, status){
                            $rootScope.defaultUrls = {
                                status: 'error'
                            };
                            ProcessErrors(null, data, status, null, {
                                hdr: 'Error',
                                msg: 'Failed to read ' + base + '. GET status: ' + status
                            });
                        });
                })
                .catch(function(data, status){
                    $rootScope.defaultUrls = {
                        status: 'error'
                    };
                    ProcessErrors(null, data, status, null, {
                        hdr: 'Error',
                        msg: 'Failed to read /api. GET status: ' + status
                    });
                });
        };
    }
])

.factory('ReturnToCaller', ['$location', 'Empty',
    function($location, Empty) {
        return function(idx) {
            var paths = $location.path().replace(/^\//, '').split('/'),
                newpath = '',
                i;
            idx = (Empty(idx)) ? paths.length - 1 : idx + 1;
            for (i = 0; i < idx; i++) {
                newpath += '/' + paths[i];
            }
            $location.path(newpath);
        };
    }
])

.factory('GetBasePath', ['$rootScope', 'Store', 'LoadBasePaths', 'Empty',
    function ($rootScope, Store, LoadBasePaths, Empty) {
        return function (set) {
            // use /api/v1/ results to construct API URLs.
            if (Empty($rootScope.defaultUrls)) {
                // browser refresh must have occurred. load from local storage
                if (Store('api')) {
                    $rootScope.defaultUrls = Store('api');
                    return $rootScope.defaultUrls[set];
                }
                return ''; //we should never get here
            }
            return $rootScope.defaultUrls[set];
        };
    }
]);

})();

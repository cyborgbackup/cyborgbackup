(function () {
  'use strict';

  angular.module('CyBorgBackup.pages.user')
    .controller('UserAddCtrl', UserAddCtrl);

  /** @ngInject */
  function UserAddCtrl($rootScope, $scope, $filter, $uibModal, $state, $location, toastr, Prompt, Wait, Rest, ProcessErrors, ReturnToCaller, GetBasePath, QuerySet) {
    var defaultUrl = GetBasePath('users');

    $scope.user = {enabled: true};

    init();
    function init(){
      $scope.isAddForm = true;
      Wait('start');
      Rest.setUrl(GetBasePath('users'));
      Rest.options()
          .then(({data}) => {
              if (!data.actions.POST) {
                  toastr.error('You do not have permission to add a user.', 'Permission Error');
                  Wait('stop');
                  $state.go("^");
              }
              Wait('stop');
          });
    }

    $scope.formCancel = function() {
        $state.go('user.list', null, { reload: true });
    };


    // Save
    $scope.formSave = function() {
        var fld, data = {};
        if (this.$ctrl.userForm.$valid) {
            Rest.setUrl(defaultUrl);
            data = $scope.user;
            Wait('start');
            Rest.post(data)
                .then(({data}) => {
                    var base = $location.path().replace(/^\//, '').split('/')[0];
                    if (base === 'user') {
                        toastr.success("New user successfully created !", "New user");
                        $state.go('user.list', null, { reload: true });
                    } else {
                        ReturnToCaller(1);
                    }
                })
                .catch(({data, status}) => {
                    toastr.error('Failed to add new user. POST returned status: ' + status, "Error!");
                });
        }
    };

  }

})();

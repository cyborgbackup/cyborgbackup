(function () {
  'use strict';

  angular.module('CyBorgBackup.pages.user')
    .controller('UserEditCtrl', UserEditCtrl);

  /** @ngInject */
  function UserEditCtrl($rootScope, $scope, $filter, $uibModal, $state, $stateParams, toastr, Prompt, Wait, Rest, ProcessErrors, GetBasePath, QuerySet) {
    var id = $stateParams.user_id,
    defaultUrl = GetBasePath('users') + id;

    init();
    function init() {
        Wait('start');
        Rest.setUrl(GetBasePath('users'));
        Rest.options()
            .then(({data}) => {
                if (!data.actions.POST) {
                    toastr.error('You do not have permission to edit a user.', 'Permission Error');
                    Wait('stop');
                    $state.go("^");
                }
            });
        Rest.setUrl(defaultUrl);
        Rest.get(defaultUrl).then(({data}) => {
                $scope.user_id = id;

                $scope.user_obj = data;
                $scope.user = data;
                $scope.name = data.name;

                //setScopeFields(data);
                Wait('stop');
            })
            .catch(({data, status}) => {
                ProcessErrors($scope, data, status, null, {
                    hdr: 'Error!',
                    msg: 'Failed to retrieve user: '+$stateParams.user_id+'. GET status: ' + status
                });
            });
    }

    $scope.formCancel = function() {
        $state.go('user.list', null, { reload: true });
    };

    $scope.formSave = function() {
        $rootScope.flashMessage = null;
        if (this.$ctrl.userForm.$valid) {
            Rest.setUrl(defaultUrl + '/');
            var data = $scope.user;
            Rest.put(data).then(() => {
                toastr.success("User "+$scope.user.email+" successfully updated !", "Update user");
                $state.go('user.list', null, { reload: true });
            })
            .catch(({data, status}) => {
                toastr.error('Failed to update user: '+$stateParams.id+'. GET status: ' + status, "Error!");
            });
        }
    };
  }

})();

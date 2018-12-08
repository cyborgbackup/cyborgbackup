(function () {
  'use strict';

  angular.module('CyBorgBackup.pages.client')
    .controller('ClientEditCtrl', ClientEditCtrl);

  /** @ngInject */
  function ClientEditCtrl($rootScope, $scope, $filter, $uibModal, $state, $stateParams, toastr, Prompt, Wait, Rest, ProcessErrors, GetBasePath, QuerySet) {
    var id = $stateParams.client_id,
    defaultUrl = GetBasePath('clients') + id;

    init();
    function init() {
        Rest.setUrl(defaultUrl);
        Wait('start');
        Rest.get(defaultUrl).then(({data}) => {
                $scope.client_id = id;

                $scope.client_obj = data;
                $scope.client = data;
                $scope.name = data.name;

                //setScopeFields(data);
                Wait('stop');
            })
            .catch(({data, status}) => {
                ProcessErrors($scope, data, status, null, {
                    hdr: 'Error!',
                    msg: 'Failed to retrieve client: '+$stateParams.client_id+'. GET status: ' + status
                });
            });
    }

    $scope.formCancel = function() {
        $state.go('client.list', null, { reload: true });
    };

    $scope.formSave = function() {
        $rootScope.flashMessage = null;
        if (this.$ctrl.clientForm.$valid) {
            Rest.setUrl(defaultUrl + '/');
            var data = $scope.client;
            Rest.put(data).then(() => {
                toastr.success("Client "+$scope.client.hostname+" successfully updated !", "Update client");
                $state.go('client.list', null, { reload: true });
            })
            .catch(({data, status}) => {
                toastr.error('Failed to update client: '+$stateParams.id+'. GET status: ' + status, "Error!");
            });
        }
    };
  }

})();

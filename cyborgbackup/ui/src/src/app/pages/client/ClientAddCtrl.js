(function () {
  'use strict';

  angular.module('CyBorgBackup.pages.client')
    .controller('ClientAddCtrl', ClientAddCtrl);

  /** @ngInject */
  function ClientAddCtrl($rootScope, $scope, $filter, $uibModal, $state, $location, toastr, Prompt, Wait, Rest, ProcessErrors, ReturnToCaller, GetBasePath, QuerySet) {
    var defaultUrl = GetBasePath('clients');

    $scope.client = {enabled: true};

    init();
    function init(){
      $scope.isAddForm = true;
      Rest.setUrl(GetBasePath('clients'));
      Rest.options()
          .then(({data}) => {
              if (!data.actions.POST) {
                  $state.go("^");
                  Alert('Permission Error', 'You do not have permission to add a client.', 'alert-info');
              }
          });
    }

    $scope.formCancel = function() {
        $state.go('client.list', null, { reload: true });
    };

    // Save
    $scope.formSave = function() {
        var fld, data = {};
        if (this.$ctrl.clientForm.$valid) {
            Rest.setUrl(defaultUrl);
            data = $scope.client;
            Wait('start');
            Rest.post(data)
                .then(({data}) => {
                    var base = $location.path().replace(/^\//, '').split('/')[0];
                    if (base === 'client') {
                        toastr.success("New client successfully created !", "New client");
                        $state.go('client.list', null, { reload: true });
                    } else {
                        ReturnToCaller(1);
                    }
                })
                .catch(({data, status}) => {
                    toastr.error('Failed to add new client. POST returned status: ' + status, "Error!");
                });
        }
    };

  }

})();

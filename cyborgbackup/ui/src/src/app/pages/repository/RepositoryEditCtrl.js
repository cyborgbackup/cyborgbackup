(function () {
  'use strict';

  angular.module('CyBorgBackup.pages.repository')
    .controller('RepositoryEditCtrl', RepositoryEditCtrl);

  /** @ngInject */
  function RepositoryEditCtrl($rootScope, $scope, $filter, $uibModal, $state, $stateParams, toastr, Prompt, Wait, Rest, ProcessErrors, GetBasePath, QuerySet) {
    var id = $stateParams.repository_id,
    defaultUrl = GetBasePath('repositories') + id;

    init();
    function init() {
        Rest.setUrl(defaultUrl);
        Wait('start');
        Rest.get(defaultUrl).then(({data}) => {
                $scope.repository_id = id;

                $scope.repository_obj = data;
                $scope.repository = data;
                $scope.name = data.name;

                //setScopeFields(data);
                Wait('stop');
            })
            .catch(({data, status}) => {
                ProcessErrors($scope, data, status, null, {
                    hdr: 'Error!',
                    msg: 'Failed to retrieve repository: '+$stateParams.repository_id+'. GET status: ' + status
                });
            });
    }

    $scope.formCancel = function() {
        $state.go('repository.list', null, { reload: true });
    };

    $scope.formSave = function() {
        $rootScope.flashMessage = null;
        if (this.$ctrl.repositoryForm.$valid) {
            Rest.setUrl(defaultUrl + '/');
            var data = $scope.repository;
            Rest.put(data).then(() => {
                toastr.success("Repository "+$scope.repository.name+" successfully updated !", "Update repository");
                  $state.go('repository.list', null, { reload: true });
            })
            .catch(({data, status}) => {
                toastr.error('Failed to update repository: '+$stateParams.id+'. GET status: ' + status, "Error!");
            });
        }
    };
  }

})();

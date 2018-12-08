(function () {
  'use strict';

  angular.module('CyBorgBackup.pages.repository')
    .controller('RepositoryAddCtrl', RepositoryAddCtrl);

  /** @ngInject */
  function RepositoryAddCtrl($rootScope, $scope, $filter, $uibModal, $state, $location, toastr, Prompt, Wait, Rest, ProcessErrors, ReturnToCaller, GetBasePath, QuerySet) {
    var defaultUrl = GetBasePath('repositories');

    $scope.repository = {enabled: true};

    init();
    function init(){
      $scope.isAddForm = true;
      Rest.setUrl(GetBasePath('repositories'));
      Rest.options()
          .then(({data}) => {
              if (!data.actions.POST) {
                  $state.go("^");
                  Alert('Permission Error', 'You do not have permission to add a repository.', 'alert-info');
              }
          });
    }

    $scope.formCancel = function() {
        $state.go('repository.list', null, { reload: true });
    };

    // Save
    $scope.formSave = function() {
        var fld, data = {};
        if (this.$ctrl.repositoryForm.$valid) {
            Rest.setUrl(defaultUrl);
            data = $scope.repository;
            Wait('start');
            Rest.post(data)
                .then(({data}) => {
                    var base = $location.path().replace(/^\//, '').split('/')[0];
                    if (base === 'repository') {
                        toastr.success("New repository successfully created !", "New repository");
                        $state.go('repository.list', null, { reload: true });
                    } else {
                        ReturnToCaller(1);
                    }
                })
                .catch(({data, status}) => {
                    toastr.error('Failed to add new repository. POST returned status: ' + status, "Error!");
                });
        }
    };

  }

})();

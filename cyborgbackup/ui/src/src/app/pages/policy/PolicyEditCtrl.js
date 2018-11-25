(function () {
  'use strict';

  angular.module('CyBorgBackup.pages.policy')
    .controller('PolicyEditCtrl', PolicyEditCtrl);

  /** @ngInject */
  function PolicyEditCtrl($rootScope, $scope, $filter, $uibModal, $state, $stateParams, toastr, Prompt, Wait, Rest, ProcessErrors, GetBasePath, QuerySet) {
    var id = $stateParams.policy_id,
    defaultUrl = GetBasePath('policies') + id;

    $scope.moduleExtraVars = false;

    init();
    function init() {
        Wait('start');
        Rest.setUrl(GetBasePath('policies'));
        Rest.options()
            .then(({data}) => {
                if (!data.actions.POST) {
                    toastr.error('You do not have permission to edit a policy.', 'Permission Error');
                    Wait('stop');
                    $state.go("^");
                }
                $scope.policyType = [];
                var typeChoices=data.actions.POST.policy_type.choices;
                typeChoices.forEach(function(item){
                    $scope.policyType.push({label: item[1], value: item[0]});
                });
                QuerySet.search(GetBasePath('schedules')).then(function(data){
                   $scope.schedules = data.data.results
                });
                QuerySet.search(GetBasePath('clients')).then(function(data){
                   $scope.clients = data.data.results
                });
                QuerySet.search(GetBasePath('repositories')).then(function(data){
                   $scope.repositories = data.data.results
                });
                QuerySet.search(GetBasePath('policies')+'vmmodule/').then(function(data){
                   $scope.vmtype = data.data;
                });
            });
        Rest.setUrl(defaultUrl);
        Rest.get(defaultUrl).then(({data}) => {
                $scope.policy_id = id;

                $scope.policy_obj = data;
                $scope.policy = data;
                $scope.name = data.name;
                if($scope.policy.extra_vars != '' && $scope.policy.policy_type == 'vm'){
                  $scope.moduleExtraVars = true;
                }

                $scope.boolean_keep_hourly = angular.isNumber($scope.policy.keep_hourly);
                $scope.boolean_keep_daily = angular.isNumber($scope.policy.keep_daily);
                $scope.boolean_keep_monthly = angular.isNumber($scope.policy.keep_monthly);
                $scope.boolean_keep_weekly = angular.isNumber($scope.policy.keep_weekly);
                $scope.boolean_keep_yearly = angular.isNumber($scope.policy.keep_yearly);

                //setScopeFields(data);
                Wait('stop');
            })
            .catch(({data, status}) => {
                ProcessErrors($scope, data, status, null, {
                    hdr: 'Error!',
                    msg: 'Failed to retrieve policy: '+$stateParams.policy_id+'. GET status: ' + status
                });
            });
    }

    $scope.checkModule = function(item, model){
      if(item['extra_vars'] != ''){
        $scope.policy.extra_vars = '{\n';
        _.forEach(item['extra_vars'], function(v){
          $scope.policy.extra_vars += '"'+v+'": "",\n'
        })
        $scope.policy.extra_vars = $scope.policy.extra_vars.substr(0, $scope.policy.extra_vars.length-2)
        $scope.policy.extra_vars += '\n}';
        $scope.moduleExtraVars = true;
      }else{
        $scope.policy.extra_vars = '';
        $scope.moduleExtraVars = false;
      }
    }

    $scope.onSelectCallback = function (item, model){
      if(model == 'mysql' || model == 'postgresql'){
        $scope.policy.extra_vars = '{\n"user":"",\n"password": ""\n}';
      }else if(model == 'piped'){
        $scope.policy.extra_vars = '{\n"command":""\n}';
      }else{
        $scope.policy.extra_vars = ''
      }
    };

    $scope.formCancel = function() {
        $state.go('policy.list', null, { reload: true });
    };

    $scope.keepChange = function(checkbox){
      if($scope['boolean_'+checkbox]){
        $scope.policy[checkbox] = null;
      }
    }

    $scope.formSave = function() {
        $rootScope.flashMessage = null;
        if (this.$ctrl.policyForm.$valid) {
            Rest.setUrl(defaultUrl + '/');
            var data = $scope.policy;
            Rest.put(data).then(() => {
                toastr.success("Policy "+$scope.policy.name+" successfully updated !", "Update policy");
                $state.go('policy.list', null, { reload: true });
            })
            .catch(({data, status}) => {
                toastr.error('Failed to update policy: '+$stateParams.id+'. GET status: ' + status, "Error!");
            });
        }
    };
  }

})();

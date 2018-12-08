(function () {
  'use strict';

  angular.module('CyBorgBackup.pages.policy')
    .controller('PolicyAddCtrl', PolicyAddCtrl);

  /** @ngInject */
  function PolicyAddCtrl($rootScope, $scope, $filter, $uibModal, $state, $location, toastr, Prompt, Wait, Rest, ProcessErrors, ReturnToCaller, GetBasePath, QuerySet) {
    var defaultUrl = GetBasePath('policies');

    $scope.policy = {enabled: true, mode_pull: false, extra_vars: ''};

    init();
    function init(){
      $scope.isAddForm = true;
      Wait('start');
      Rest.setUrl(GetBasePath('policies'));
      Rest.options()
          .then(({data}) => {
              if (!data.actions.POST) {
                  toastr.error('You do not have permission to add a policy.', 'Permission Error');
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

              $scope.boolean_keep_hourly = false;
              $scope.boolean_keep_daily = false;
              $scope.boolean_keep_monthly = false;
              $scope.boolean_keep_weekly = false;
              $scope.boolean_keep_yearly = false;
              Wait('stop');
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

    $scope.keepChange = function(checkbox){
      if($scope['boolean_'+checkbox]){
        $scope.policy[checkbox] = null;
      }
    }

    $scope.formCancel = function() {
        $state.go('policy.list', null, { reload: true });
    };


    // Save
    $scope.formSave = function() {
        var fld, data = {};
        if (this.$ctrl.policyForm.$valid) {
            Rest.setUrl(defaultUrl);
            data = $scope.policy;
            Wait('start');
            Rest.post(data)
                .then(({data}) => {
                    var base = $location.path().replace(/^\//, '').split('/')[0];
                    if (base === 'policy') {
                        toastr.success("New policy successfully created !", "New policy");
                        $state.go('policy.list', null, { reload: true });
                    } else {
                        ReturnToCaller(1);
                    }
                })
                .catch(({data, status}) => {
                    toastr.error('Failed to add new policy. POST returned status: ' + status, "Error!");
                });
        }
    };

  }

})();

(function () {
  'use strict';

  angular.module('CyBorgBackup.pages.setting')
    .controller('SettingListCtrl', SettingListCtrl);

  /** @ngInject */
  function SettingListCtrl($scope, $filter, $uibModal, $state, toastr, Prompt, Wait, Rest, ProcessErrors, GetBasePath, QuerySet) {
    $scope.tablePageSize = 10;
    let path = GetBasePath('settings');

    function init(){
      QuerySet.search(path).then(function(data){
        var settings = []
        _.forEach(data.data.results, function(v){
          if(v.setting_type == 'boolean'){
            v.value = (v.value == 'True')
          }
          v.encrypted = false;
          if(/\$encrypted\$/.test(v.value)){
            v.encrypted = true;
            if(v.setting_type == 'privatekey'){
              v.value = 'ENCRYPTED';
            }else{
              v.value = '';
            }
          }
          settings.push(v)
        });
         $scope.settings = settings;
      });
    }
    init();

    $scope.replaceEncrypted = function(form, obj){
      obj.encrypted = false;
      obj.value = '';
    }

    $scope.formSave = function () {
      var url = GetBasePath('settings');
      var fld;
      var promises = [];
      var latest;
      for (fld in $scope.settings) {
         let field = $scope.settings[fld];
         if(! /\$encrypted\$/.test(field) && !field.encrypted && field.value !== ''){
             let path = `${GetBasePath('settings')}?key=${field.key}`;
             Rest.setUrl(path);
             Rest.get().then(({data}) => {
                 if(data.count == 1) {
                     let seturl = data.results[0].url;
                     if( field.value !== data.results[0].value) {
                         Rest.setUrl(seturl);
                         Rest.patch({value: field.value}).then(function(){
                           if(latest.id == field.id){
                             toastr.success('Settings updated. ', "Success!");
                             init();
                           }
                         }).catch(function(error){
                           toastr.error('Failed to update settings. ' + error.data, "Error!");
                         });
                         latest = field;
                     }
                 }
             });
          }
        };
      };
  };

})();

(function () {
  'use strict';

  angular.module('CyBorgBackup.pages.catalog')
    .controller('CatalogListCtrl', CatalogListCtrl);

  /** @ngInject */
  function CatalogListCtrl($scope, $filter, $uibModal, $state, toastr, Prompt, Wait, Rest, ProcessErrors, GetBasePath, QuerySet) {
    $scope.tablePageSize = 10;
    let path = GetBasePath('catalogs');
    $.jstree.defaults.core.themes.url = true;
    $.jstree.defaults.core.themes.dir = "assets/img/theme/vendor/jstree/dist/themes";
    var newId=1;

    $scope.basicConfig = {
      core: {
        multiple: false,
        animation: true,
        check_callback: true,
        worker: true
      },
      'types': {
        'folder': {
          'icon': 'ion-ios-folder'
        },
        'default': {
          'icon': 'ion-document-text'
        }
      },
      'plugins': ['types'],
      'version': 1
    };

    $scope.openode = function(e, data){
      var curNode = data.node;
      var url, url_info;
      if(curNode.parent == '#'){
        url = path+'?archive_name='+curNode.text+'&path__regex=^[^/]*$&order=path';
        QuerySet.search(path+'?archive_name='+curNode.text).then(function(data){
          var a_catalog_entry = data.data.results[0];
          QuerySet.search(GetBasePath('jobs')+a_catalog_entry.job+'/').then(function(data){
            $scope.currentBackup = data.data;
          });
        });
      }else{
        var master_item = _.find($scope.treeData, { id : curNode.parents[curNode.parents.length-2] } );
        url = path+'?archive_name='+master_item.text+'&path__regex=^'+curNode.text+'/[^/]*$&order=path';
        QuerySet.search(path+'?archive_name='+master_item.text+'&path='+curNode.text).then(function(data){
          $scope.currentElement = data.data.results[0];
        });
      }
      QuerySet.search(url).then(function(data){
        if(curNode.children.length == 0){
          _.forEach(data.data.results, function(v){
            var type;
            if(v.mode[0] == 'd'){
              type = 'folder';
            }else{
              type = 'default';
            }
            $scope.treeData.push({id: (newId++).toString(), parent: curNode.id, children: [], type: type, text: v['path']});
          });
        }
        _.forEach(curNode.parents, function(v){
          if(v != '#'){
            _.find($scope.treeData, { id : v } ).state = {opened: true};
          }
        });
        _.find($scope.treeData, { id : curNode.id } ).state = {opened: true};
        $scope.basicConfig.version ++;
      });
    }

    QuerySet.search(path+'?fields=archive_name&order=-archive_name').then(function(data){
       var archives = data.data.results;
       var entries_tree = [];
       _.forEach(archives, function(v){
         entries_tree.push({id: (newId++).toString(), 'parent': '#', 'type': 'folder', children: [], 'text': v['archive_name']});
       })
       $scope.treeData = entries_tree;
    });

  }

})();

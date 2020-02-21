// Copyright 2020 The Oppia Authors. All Rights Reserved.
//
// Licensed under the Apache License, Version 2.0 (the "License");
// you may not use this file except in compliance with the License.
// You may obtain a copy of the License at
//
//      http://www.apache.org/licenses/LICENSE-2.0
//
// Unless required by applicable law or agreed to in writing, software
// distributed under the License is distributed on an "AS-IS" BASIS,
// WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
// See the License for the specific language governing permissions and
// limitations under the License.

/**
 * @fileoverview Unit test for TopicCreationBackendApiService.
 */

import {  TopicCreationBackendApiService } from
'domain/topic/topic-creation-backend-api.service.ts'
import { UpgradedServices } from 'services/UpgradedServices';
import { TestBed, fakeAsync } from '@angular/core/testing';
import { HttpClientTestingModule, HttpTestingController } from '@angular/common/http/testing';

describe('Topic creation backend api service', function() {
  let topicCreationBackendApiService = null;
  let httpTestingController: HttpTestingController;
  beforeEach(angular.mock.module('oppia'));

  beforeEach(angular.mock.module('oppia', function($provide) {
    var ugs = new UpgradedServices();
    for (let [key, value] of Object.entries(ugs.getUpgradedServices())) {
      $provide.value(key, value);
    }
  }));

  beforeEach(() => {
    TestBed.configureTestingModule({
      imports: [HttpClientTestingModule],
    });
    httpTestingController = TestBed.get(HttpTestingController);
    topicCreationBackendApiService = TestBed.get(
      TopicCreationBackendApiService);
  });

  afterEach(()=> {
    httpTestingController.verify();
  });

  it('should successfully create a new topic and obtain the skill ID',
    () => {
      var successHandler = jasmine.createSpy('success');
      var failHandler = jasmine.createSpy('fail');

      topicCreationBackendApiService.createTopic(
        'topic-name', 'topic-abbr-name').then(successHandler, failHandler);
        var req = httpTestingController.expectOne(
          '/topic_data_handler/0');
        expect(req.request.method).toEqual('POST');
        req.flush(sampleDataResults);
    
    });

  it('should fail to create a new topic and call the fail handler',
    fakeAsync(() => {
      var successHandler = jasmine.createSpy('success');
      var failHandler = jasmine.createSpy('fail');

      $httpBackend.expectPOST('/topic_editor_handler/create_new').respond(
        500, 'Error creating a new topic.');
      TopicCreationBackendApiService.createTopic(
        'topic-name', 'topic-abbr-name').then(
        successHandler, failHandler);
      $httpBackend.flush();
      expect(successHandler).not.toHaveBeenCalled();
      expect(failHandler).toHaveBeenCalledWith(
        'Error creating a new topic.');
    });
});

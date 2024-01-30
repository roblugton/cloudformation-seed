import itertools
import tempfile
import unittest
import yaml
from unittest import mock
from cloudformation_seed.cfn_template import CloudformationCollection

flat_stacks = """
stacks:
    - name: service1
      template: service1.cf.yaml
      parameters:
        foo: bar
    - name: service2
      template: service2.cf.yaml
      parameters:
        foo: baz
"""

two_substacks_three_stacks = """
stacks:
  databases:
    - name: database1
      template: database1.cf.yaml
      parameters:
        foo: bar
  services:
    - name: service1
      template: service1.cf.yaml
      parameters:
        foo: baz
    - name: service2
      template: service2.cf.yaml
      parameters:
        foo: boogers
"""

mock_template_file = """
Description: Mock CFN template file
Parameters:
  Foo:
    Type:String
    Default: foo
Resources:
  Thing:
    Type: AWS::THING
    Parameters:
      Foo: !Ref Foo
"""

class TestCloudformationCollection(unittest.TestCase):
    
    def setUp(self) -> None:
      self.tf = tempfile.NamedTemporaryFile(mode='w')
      self.tf.write(mock_template_file) 

    @mock.patch('cloudformation_seed.cfn_template.CloudformationCollection.find_template_file')
    def test_parse_stacks_no_substacks(self, mock_find_template_file):
        y = yaml.safe_load(flat_stacks)
        mock_find_template_file.return_value = self.tf.name
        
        with self.subTest("when substack_name is not set"):
          c = CloudformationCollection('foo', 'foo', 'foo', y)
          s = c.stacks
          self.assertEqual(len(s), 2, 'should be reading 2 stacks')
          self.assertEqual(s[0]['name'], 'service1', 'first service should be service1')
          self.assertEqual(s[1]['name'], 'service2', 'second service should be service2')
        
        with self.subTest("when substack_name is set"):
          c = CloudformationCollection('foo', 'foo', 'foo', y, 'services')
          s = c.stacks
          self.assertEqual(len(s), 2, 'should be reading 2 stacks')
          self.assertEqual(s[0]['name'], 'service1', 'first service should be service1')
          self.assertEqual(s[1]['name'], 'service2', 'second service should be service2')
        
    @mock.patch('cloudformation_seed.cfn_template.CloudformationCollection.find_template_file')
    def test_parse_stacks_with_substacks(self, mock_find_template_file):
        y = yaml.safe_load(two_substacks_three_stacks)
        mock_find_template_file.return_value = self.tf.name
        
        with self.subTest("when substack_name is not set"):
          c = CloudformationCollection('foo', 'foo', 'foo', y)
          s = c.stacks
          self.assertEqual(len(s), 3, 'should be reading 3 stacks')
          self.assertEqual(s[0]['name'], 'database1', 'first service should be database1')
          self.assertEqual(s[1]['name'], 'service1', 'second service should be service1')
          self.assertEqual(s[2]['name'], 'service2', 'third service should be service2')

        with self.subTest("when substack_name is set"):
          c = CloudformationCollection('foo', 'foo', 'foo', y, 'services')
          s = c.stacks
          self.assertEqual(len(s), 2, 'should be reading 2 stacks')
          self.assertEqual(s[0]['name'], 'service1', 'first service should be service1')
          self.assertEqual(s[1]['name'], 'service2', 'second service should be service2')
          
    def tearDown(self) -> None:
      self.tf.close()



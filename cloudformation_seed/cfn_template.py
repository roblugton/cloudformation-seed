from cloudformation_seed import s3_classes, util

from typing import Dict, List, Any, Tuple
from colorama import Fore, Style

import os
import yaml
import hashlib
import logging

log = logging.getLogger('stack-deployer')


class CloudformationTemplateBody:
    def __init__(self, template_text: str) -> None:
        self.text = template_text
        self.checksum = self.calculate_checksum(self.text)
        self.body: Dict[str, Any] = yaml.load(template_text, Loader=util.IgnoreYamlLoader)

    @property
    def parameters(self) -> Dict[str, Dict[str, str]]:
        return self.body.get('Parameters', dict())

    def calculate_checksum(self, text) -> str:
        sha1sum = hashlib.sha1()
        sha1sum.update(bytes(self.text, 'utf-8'))
        return sha1sum.hexdigest()


class CloudformationTemplate(object):
    def __init__(self, s3_bucket: Any, template_key: str, s3_key_prefix: str,
                    file_path: str, template_parameters: Dict[str, Any]) -> None:
        self.template_key: str = template_key
        self.template_parameters: Dict[str, Any] = template_parameters
        if s3_bucket and file_path:
            self.template_body: CloudformationTemplateBody = self.load_template_file(file_path)
            generated_key = self.build_s3_key(self.template_key, self.template_checksum)
            self.s3_key = f'{s3_key_prefix}/{generated_key}'
            self.o: s3_classes.S3Uploadable = \
                s3_classes.S3Uploadable(file_path, s3_bucket, self.s3_key)
        elif template_key.startswith("s3://"):
            r = util.session.resource('s3')
            s3_bucket_name, self.s3_key = template_key.replace("s3://", "").split("/", 1)
            log.debug(f'Using external template in bucket {s3_bucket_name} with key {self.s3_key}')
            s3_bucket = r.Bucket(s3_bucket_name)
            self.o = s3_classes.S3Downloadble(s3_bucket, self.s3_key)

    @property
    def name(self) -> str:
        return self.template_parameters['name']

    @property
    def tags(self):
        if 'tags' in self.template_parameters:
            return self.template_parameters['tags']
        else:
            return []

    @property
    def template(self) -> str:
        return self.template_parameters['template']

    @property
    def template_checksum(self) -> str:
        return self.template_body.checksum

    @property
    def template_type(self) -> str:
        return self.template_parameters.get('type', 'stack')

    @property
    def template_s3_key(self) -> str:
        return self.o.s3_key

    @property
    def template_url(self) -> str:
        return self.o.s3_url

    def build_s3_key(self, template_key, template_checksum) -> str:
        if self.template_parameters.get('predictable_name', False) is True:
            return template_key
        return '/'.join([os.path.dirname(template_key),
            f'{template_checksum}-{os.path.basename(template_key)}']).strip('/')

    def load_template_file(self, file_path: str) -> CloudformationTemplateBody:
        log.info(f'Loading template for stack {Fore.GREEN}{self.name}{Style.RESET_ALL} '
            f'from {Fore.GREEN}{file_path}{Style.RESET_ALL}...')
        with open(file_path, 'r') as f:
            return CloudformationTemplateBody(f.read())

    def sync(self) -> None:
        if self.o and isinstance(self.o, s3_classes.S3Uploadable):
            self.o.upload()
        if self.o and isinstance(self.o, s3_classes.S3Downloadble):
            self.o.download()
            self.template_body: CloudformationTemplateBody = self.load_template_file(self.o.local_path)



class CloudformationCollection(util.DirectoryScanner):
    def __init__(self, path: str, s3_bucket: Any, s3_key_prefix: str,
                    environment_parameters: Dict['str', Any], substack_name: str = '') -> None:
        self.s3_bucket: Any = s3_bucket
        self.environment_parameters: Dict['str', Any] = environment_parameters
        self.substack_name: str = substack_name
        self.template_files: List[Tuple[str, str]] = self.scan_directories(path, '**/*.cf.yaml')
        util.log_section('Collecting templates included in the environment')
        self.templates: List[CloudformationTemplate] = []
        self.stacks: List[Tuple[str, str]] = self.parse_stacks()
        for xs in self.stacks:
            template_key = xs['template']
            # use s3 path
            if template_key.startswith("s3://"):
                template = CloudformationTemplate(
                    None,
                    template_key,
                    None,
                    None,
                    xs
                )
            else:
                # find local file
                template = CloudformationTemplate(
                    self.s3_bucket,
                    xs['template'],
                    s3_key_prefix,
                    self.find_template_file(template_key),
                    xs
                )
            self.templates.append(template)

        util.log_section('Collecting templates not included in the environment')
        for xf in self.template_files:
            if len([xt for xt in self.templates if xt.template_key == xf[0]]) > 0:
                continue
            self.templates.append(CloudformationTemplate(
                self.s3_bucket,
                xf[0],
                s3_key_prefix,
                xf[1],
                {
                    'name': xf[0],
                    'template': xf[0]
                })
            )
        util.log_section('Done collecting templates')

    def parse_stacks(self) -> List[Tuple[str, str]]:
        stacks = list()
        raw_stacks = self.environment_parameters.get('stacks')
        if raw_stacks and isinstance(raw_stacks, List):
            return raw_stacks
        if raw_stacks and isinstance(raw_stacks, Dict):
            if raw_stacks.get(self.substack_name, None) is not None:
               stacks.extend(raw_stacks[self.substack_name])
               return stacks
            if self.substack_name == '':
                for xs in raw_stacks:
                    stacks.extend(raw_stacks[xs])
                return stacks
            raise util.InvalidStackConfiguration(f"Unable to find substack '{self.substack_name}' in stacks '{[key for key in raw_stacks.keys()]}'")
        raise util.InvalidStackConfiguration(f'Invalid stacks definition')
        

    def list_deployable(self) -> List[CloudformationTemplate]:
        u = list()
        for xs in self.stacks:
            try:
                if xs.get('deployable', True) is False:
                    log.info(f'Stack {Fore.GREEN}{xs.get("name")}{Style.RESET_ALL} is not deployable, skipping')
                    continue
                stack_template = [xt for xt in self.templates if xt.name == xs.get('name')].pop()
                u.append(stack_template)
            except IndexError:
                raise util.InvalidStackConfiguration(f'Template not found for {xs.get("name")}') from None
        return u

    def find_template(self, template_name: str) -> CloudformationTemplate:
        try:
            return [x for x in self.templates if x.template == template_name].pop()
        except IndexError:
            raise util.InvalidStackConfiguration(f'Template {template_name} not found in this deployment')\
                from None

    def find_template_file(self, template_key: str) -> str:
        for xk, xp in self.template_files:
            if xk == template_key:
                return xp
        raise util.InvalidStackConfiguration(f'Template file not found for {template_key}')

    def sync(self) -> None:
        for xt in [xt for n, xt in enumerate(self.templates)
                        if xt.template not in [xxt.template for xxt in self.templates[:n]]]:
            xt.sync()

"""Main module."""

import pandas as pd
import pickle
import os
from pathlib import Path
from igel.utils import read_yaml, extract_params, _reshape
from igel.data import evaluate_model
from igel.data import models_dict, metrics_dict
import json
import warnings
import logging

warnings.filterwarnings("ignore")
logging.basicConfig(format='%(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)


class IgelModel(object):
    """
    IgelModel is the base model to use the fit, evaluate and predict functions of the sklearn library
    """
    commands = ('fit', 'evaluate', 'predict')
    model_types = ('regression', 'classification')
    command = None
    model_path = None
    model = None
    target = None
    features = None
    stats_dir = 'model_results'
    res_path = Path(os.getcwd()) / stats_dir
    save_to = 'model.sav'

    def __init__(self, command: str, **cli_args):
        logger.info(f"CLI args: { cli_args}")
        logger.info(f"Command: { command}")
        if command not in self.commands:
            logger.exception(f"Please choose an existing command -> {self.commands}")

        self.command = command
        self.data_path = cli_args.get('data_path')

        if self.command == "fit":
            self.model_definition_file = cli_args.get('yaml_path')
            self.yaml_config = read_yaml(self.model_definition_file)
            logger.info(f"model configuration: {self.yaml_config}")

            self.model_type, self.target, self.algorithm = extract_params(self.yaml_config)

        else:
            self.model_path = cli_args.get('model_path')
            with open(self.res_path / 'description.json', 'r') as f:
                dic = json.load(f)
                self.target = dic.get("target")
                self.model_type = dic.get("type")

    def _create_model(self, model_type: str, model_algorithm: str):
        """
        fetch a model depending on the provided type and algorithm by the user and return it
        @param model_type: type of the model -> whether regression or classification
        @param model_algorithm: specific algorithm to use
        @return: class of the chosen model
        """
        assert model_type in self.model_types, "model type is not supported"
        algorithms = models_dict.get(model_type)  # extract all algorithms as a dictionary
        model = algorithms.get(model_algorithm)  # extract model class depending on the algorithm
        if not model:
            raise Exception("Model not found in the algorithms list")
        else:
            return model

    def _save_model(self, model, save_to: str):
        """
        save the model to a binary file
        @param model: model to save
        @param save_to: path where to save the model
        @return: bool
        """
        cwd = Path(os.getcwd())
        self.res_path = cwd / self.stats_dir
        try:
            if not os.path.exists(self.res_path):
                os.mkdir(self.res_path)
            else:
                logger.info(f"{self.stats_dir} already exists in the path")
                logger.warning(f"data in the {self.stats_dir} folder will be overridden")

        except OSError:
            logger.exception("Creation of the directory %s failed" % self.stats_dir)
        else:
            logger.info("Successfully created the directory %s " % self.stats_dir)
            pickle.dump(model, open(self.res_path / save_to, 'wb'))
            return True

    def _load_model(self, f: str):
        """
        load a saved model from file
        @param f: path to model
        @return: loaded model
        """
        try:
            if not f:
                path = self.res_path / self.save_to
                logger.info(f"result path: {self.res_path} | saved to: {self.save_to}")
                logger.info(f"loading model form {path} ")
                model = pickle.load(open(path, 'rb'))
            else:
                logger.info(f"loading from {f}")
                model = pickle.load(open(f, 'rb'))
            return model
        except FileNotFoundError:
            logger.error(f"File not found in {self.res_path / self.save_to}")

    def _prepare_fit_data(self):
        return self._process_data()

    def _prepare_val_data(self):
        return self._process_data()

    def _process_data(self):
        """
        read and return data as x and y
        @return: list of separate x and y
        """
        assert isinstance(self.target, list), "provide target(s) as a list in the yaml file"
        assert len(self.target) > 0, "please provide at least a target to predict"
        try:
            dataset = pd.read_csv(self.data_path)
            logger.info(f"dataset shape: {dataset.shape}")
            self.features = list(dataset.columns)

            if any(col not in self.features for col in self.target):
                raise Exception("chosen targets to predict must exist in the dataset")

            y = pd.concat([dataset.pop(x) for x in self.target], axis=1)
            x = _reshape(dataset.to_numpy())
            y = _reshape(y.to_numpy())
            logger.info(f"y shape: {y.shape} and x shape: {x.shape}")
            return x, y

        except Exception as e:
            logger.exception(f"error occured while preparing the data: {e.args}")

    def _prepare_predict_data(self):
        """
        read and return x_pred
        @return: x_pred
        """
        try:
            x_val = pd.read_csv(self.data_path)
            logger.info(f"shape of the prediction data: {x_val.shape}")
            return _reshape(x_val)
        except Exception as e:
            logger.exception(f"exception while preparing prediction data: {e}")

    def fit(self, *args, **kwargs):
        """
        fit a machine learning model and save it to a file along with a description.json file
        @return: None
        """
        model_class = self._create_model(self.model_type, self.algorithm)
        self.model = model_class()
        logger.info(f"executing a {self.model.__class__.__name__} algorithm ..")
        x, y = self._prepare_fit_data()
        self.model.fit(x, y)
        saved = self._save_model(self.model, save_to=self.save_to)
        if saved:
            logger.info(f"model saved successfully and can be found in the {self.stats_dir} folder")

        fit_description = {
            "model": self.model.__class__.__name__,
            "type": self.model_type,
            "data_path": self.data_path,
            "results_path": str(self.res_path),
            "model_path": str(self.res_path),
            "target": self.target
        }

        try:
            json_file = self.res_path / "description.json"
            logger.info(f"saving fit description to {json_file}")
            with open(json_file, 'w', encoding='utf-8') as f:
                json.dump(fit_description, f, ensure_ascii=False, indent=4)
        except Exception as e:
            logger.exception(f"Error while storing the fit description file: {e}")

    def evaluate(self, *args, **kwargs):
        """
        evaluate a pre-fitted model and save results to a evaluation.json
        @return: None
        """
        try:
            model = self._load_model(f=self.model_path)
            x_val, y_true = self._prepare_val_data()
            y_pred = model.predict(x_val)
            eval_results = evaluate_model(model_type=self.model_type,
                                          y_pred=y_pred,
                                          y_true=y_true,
                                          **kwargs)

            eval_file = self.res_path / "evaluation.json"
            logger.info(f"saving fit description to {eval_file}")
            with open(eval_file, 'w', encoding='utf-8') as f:
                json.dump(eval_results, f, ensure_ascii=False, indent=4)

        except Exception as e:
            logger.exception(f"error occured during evaluation: {e}")

    def predict(self, *args, **kwargs):
        """
        use a pre-fitted model to make predictions and save them as csv
        @return: None
        """
        try:
            model = self._load_model(f=self.model_path)
            x_val = self._prepare_predict_data()
            y_pred = model.predict(x_val)
            y_pred = _reshape(y_pred)
            logger.info(f"predictions array type: {type(y_pred)}")
            logger.info(f"predictions shape: {y_pred.shape} | shape len: {len(y_pred.shape)}")
            logger.info(f"predict on targets: {self.target}")
            df_pred = pd.DataFrame.from_dict({self.target[i]: y_pred[:, i] if len(y_pred.shape) > 1 else y_pred for i in range(len(self.target))})

            path = self.res_path / 'predictions.csv'
            logger.info(f"saving the predictions to {path}")
            df_pred.to_csv(path)

        except Exception as e:
            logger.exception(f"Error while preparing predictions: {e}")


if __name__ == '__main__':
    mock_params = {'data_path': '/home/nidhal/my_projects/igel/examples/data/example.csv',
                   'model_definition_file': '/home/nidhal/my_projects/igel/examples/model.yaml'}

    reg = IgelModel('fit', **mock_params)
    reg.fit()
    reg.predict()

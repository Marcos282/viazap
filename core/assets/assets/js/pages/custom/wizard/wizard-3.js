"use strict";

// Class definition
var KTWizard3 = function () {
	// Base elements
	var _wizardEl;
	var _formEl;
	var _wizard;
	var _validations = [];

	// Private functions
	var initWizard = function () {
		// Initialize form wizard
		_wizard = new KTWizard(_wizardEl, {
			startStep: 1, // initial active step number
			clickableSteps: true  // allow step clicking
		});

		// Validation before going to next page
		_wizard.on('beforeNext', function (wizard) {
			// Don't go to the next step yet
			_wizard.stop();

			// Validate form
			var currentStep = wizard.getStep();
			var validatorIndex = currentStep - 1;
			var validator = _validations[validatorIndex];
			
			if (validator && typeof validator.validate === 'function') {
				validator.validate().then(function (status) {
					if (status == 'Valid') {
						_wizard.goNext();
						KTUtil.scrollTop();
					} else {
						Swal.fire({
							text: "Parece que alguns campos obrigatórios não foram preenchidos, por favor verifique.",
							icon: "error",
							buttonsStyling: false,
							confirmButtonText: "Ok, entendi!",
							customClass: {
								confirmButton: "btn font-weight-bold btn-light"
							}
						}).then(function () {
							KTUtil.scrollTop();
						});
					}
				}).catch(function(error) {
					// Se houver erro na validação, permite ir para o próximo step
					_wizard.goNext();
					KTUtil.scrollTop();
				});
			} else {
				_wizard.goNext();
				KTUtil.scrollTop();
			}
		});

		// Change event
		_wizard.on('change', function (wizard) {
			KTUtil.scrollTop();
		});
	}

	var initValidation = function () {
		// Init form validation rules. For more info check the FormValidation plugin's official documentation:https://formvalidation.io/
		// Step 1
		_validations.push(FormValidation.formValidation(
			_formEl,
			{
				fields: {
					name: {
						validators: {
							notEmpty: {
								message: 'Campo nome é obrigatório'
							}
						}
					},
					descricao_loja: {
						validators: {
							notEmpty: {
								message: 'Campo descrição da loja é obrigatório'
							}
						}
					},
					// cidade: {
					// 	validators: {
					// 		notEmpty: {
					// 			message: 'Campo cidade é obrigatório'
					// 		}
					// 	}
					// },
					estado: {
						validators: {
							notEmpty: {
								message: 'Campo estado é obrigatório'
							}
						}
					},
					rua: {
						validators: {
							notEmpty: {
								message: 'Campo rua é obrigatório'
							}
						}
					},
					numero_endereco: {
						validators: {
							notEmpty: {
								message: 'Campo número é obrigatório'
							}
						}
					},							
				},
				plugins: {
					trigger: new FormValidation.plugins.Trigger(),
					bootstrap: new FormValidation.plugins.Bootstrap()
				}
			}
		));

		// Step 2
		_validations.push(FormValidation.formValidation(
			_formEl,
			{
				fields: {
					package: {
						validators: {
							notEmpty: {
								message: 'Package details is required'
							}
						}
					},
					
				},
				plugins: {
					trigger: new FormValidation.plugins.Trigger(),
					bootstrap: new FormValidation.plugins.Bootstrap()
				}
			}
		));

		// Step 3
		_validations.push(FormValidation.formValidation(
			_formEl,
			{
				fields: {
					delivery: {
						validators: {
							notEmpty: {
								message: 'Delivery type is required'
							}
						}
					},
					packaging: {
						validators: {
							notEmpty: {
								message: 'Packaging type is required'
							}
						}
					},
					preferreddelivery: {
						validators: {
							notEmpty: {
								message: 'Preferred delivery window is required'
							}
						}
					}
				},
				plugins: {
					trigger: new FormValidation.plugins.Trigger(),
					bootstrap: new FormValidation.plugins.Bootstrap()
				}
			}
		));

		// Step 4
		_validations.push(FormValidation.formValidation(
			_formEl,
			{
				fields: {
					locaddress1: {
						validators: {
							notEmpty: {
								message: 'Address is required'
							}
						}
					},
					locpostcode: {
						validators: {
							notEmpty: {
								message: 'Postcode is required'
							}
						}
					},
					loccity: {
						validators: {
							notEmpty: {
								message: 'City is required'
							}
						}
					},
					locstate: {
						validators: {
							notEmpty: {
								message: 'State is required'
							}
						}
					},
					loccountry: {
						validators: {
							notEmpty: {
								message: 'Country is required'
							}
						}
					}
				},
				plugins: {
					trigger: new FormValidation.plugins.Trigger(),
					bootstrap: new FormValidation.plugins.Bootstrap()
				}
			}
		));

		// Step 5 - Notificações
		_validations.push(FormValidation.formValidation(
			_formEl,
			{
				fields: {
					dummy_field_step5: {
						validators: {}
					}
				},
				plugins: {
					trigger: new FormValidation.plugins.Trigger(),
					bootstrap: new FormValidation.plugins.Bootstrap()
				}
			}
		));

		// Step 6 - Contato/Review
		_validations.push(FormValidation.formValidation(
			_formEl,
			{
				fields: {
					dummy_field_step6: {
						validators: {}
					}
				},
				plugins: {
					trigger: new FormValidation.plugins.Trigger(),
					bootstrap: new FormValidation.plugins.Bootstrap()
				}
			}
		));
	}

	return {
		// public functions
		init: function () {
			_wizardEl = KTUtil.getById('kt_wizard_v3');
			_formEl = KTUtil.getById('kt_form');

			initWizard();
			initValidation();
		}
	};
}();

jQuery(document).ready(function () {
	KTWizard3.init();
});

import {
  showErrorMessage,
  showSuccessMessage,
} from '/static/js/common/notification.prod.js';

document.addEventListener('DOMContentLoaded', function () {
  let csrfToken = document.querySelector('[name=csrftoken]').content;
  $('.actionButton').on('click', function () {
    let $content = $('.mobileHeaderContent');
    if ($content.hasClass('animate__fadeInDown')) {
      $('.mobileHeaderContent')
        .removeClass('animate__fadeInDown')
        .addClass('animate__fadeOutUp');
      $('#header').toggleClass('darken', false);
    } else {
      $('.mobileHeaderContent')
        .removeClass('animate__fadeOutUp')
        .addClass('animate__fadeInDown');
      $('#header').toggleClass('darken', true);
    }
  });

  $('.mobileHeaderContent').on('click', function () {
    $(this).removeClass('animate__fadeInDown').addClass('animate__fadeOutUp');
    $('#header').toggleClass('darken', false);
  });

  $('.newsletter-button').on('click', function () {
    let newsletterInput = $('.newsletter-input-container').find('input');

    if (newsletterInput.val()) {
      let $modalContainer = $('.modal-container');
      $modalContainer.find('#modalHeader').text('Join Our Newsletter');
      $modalContainer
        .find('.modalContentHolder')
        .append(
          $(
            `<div class="inputHolder"><input type="text" id="newsletterEmail" value="${newsletterInput.val()}"></div>`
          )
        )
        .append(
          $(`
            <div class="inputHolder flex">
                <div class="modalInput">
                    <input type="text" id="newsletterFirstName" placeholder="Enter your First Name">
                </div>
                <div class="modalInput">
                    <input type="text" id="newsletterLastName" placeholder="Enter your Last Name">
                </div>
            </div>
            `)
        );
      $modalContainer
        .removeClass('animate__fadeOut')
        .toggleClass('animate__fadeIn', true);
      $('#modal-value').val('newsletter');
    } else {
      showErrorMessage('Invalid Email', 'Kindly enter a valid email.');
    }
  });
  $('#cancel').on('click', function () {
    let $modalContainer = $('.modal-container');
    $modalContainer
      .removeClass('animate__fadeIn')
      .addClass('animate__fadeOut')
      .one('animationend', function () {
        $(this).find('#modalHeader').text('');
        $(this).find('.modalContentHolder').empty();
      });
  });

  $('#accept').on('click', function () {
    let modal = $('#modal-value').val();
    let email = $('#newsletterEmail').val().trim();
    let firstName = $('#newsletterFirstName').val().trim();
    let lastName = $('#newsletterLastName').val().trim();
    firstName = firstName.charAt(0).toUpperCase() + firstName.slice(1);
    lastName = lastName.charAt(0).toUpperCase() + lastName.slice(1);
    if (modal == 'newsletter' && email && firstName && lastName) {
      $.ajax({
        type: 'POST',
        headers: {
          'X-CSRFToken': csrfToken,
        },
        contentType: 'application/json',
        data: JSON.stringify({
          email: email,
          firstName: firstName,
          lastName: lastName,
        }),
        processData: false,
        url: '/users/?action=register-newsletter',
        success: function () {
          showSuccessMessage(
            gettext('Subscribed'),
            gettext('You have successfully subscribed to SmSt Newsletter')
          );
        },
        error: function () {},
      });
    }
  });

  if (!localStorage.getItem('cookie_acceptance')) {
    $('#cookie_banner').fadeIn();
  }

  $('#accept_cookies').on('click', function () {
    $('.cookie_policy_holder')
      .removeClass('animate__fadeInUp')
      .addClass('animate__fadeOutDown')
      .one('animationend', function () {
        localStorage.setItem('cookie_acceptance', true);
        showSuccessMessage(
          'Cookie Preference Set',
          'You have accepted our Cookie Policy'
        );
        $('#cookie_banner').remove();
      });
  });
});

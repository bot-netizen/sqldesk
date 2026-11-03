import React, { useState, useEffect } from "react";
import { UserProfile } from "@/components/proptypes";
import UserAvatar from "@/components/UserAvatar";

import UserInfoForm from "./UserInfoForm";
import ApiKeyForm from "./ApiKeyForm";
import PasswordForm from "./PasswordForm";
import ToggleUserForm from "./ToggleUserForm";
import UserAccess from "./UserAccess";
import ConnectedApps from "./ConnectedApps";

export default function EditableUserProfile(props) {
  const [user, setUser] = useState(props.user);

  useEffect(() => {
    setUser(props.user);
  }, [props.user]);

  return (
    <div className="col-md-4 col-md-offset-4">
      {/*
        `UserAvatar`, not a bare <img>: almost nobody has a picture --
        gravatar was taken out, so `profile_image_url` is normally null --
        and an <img> with no src draws the browser's broken-image glyph
        and its alt text. Which is what this page showed everybody.
      */}
      <UserAvatar
        user={{ name: user.name, email: user.email, profile_image_url: user.profileImageUrl }}
        size={40}
        className="profile__image"
      />
      <h3 className="profile__h3">{user.name}</h3>
      <hr />
      <UserInfoForm user={user} onChange={setUser} />
      {!user.isDisabled && (
        <React.Fragment>
          <ApiKeyForm user={user} onChange={setUser} />
          <ConnectedApps user={user} />
          <hr />
          <PasswordForm user={user} />
        </React.Fragment>
      )}
      <hr />
      <UserAccess user={user} />
      <hr />
      <ToggleUserForm user={user} onChange={setUser} />
    </div>
  );
}

EditableUserProfile.propTypes = {
  user: UserProfile.isRequired,
};

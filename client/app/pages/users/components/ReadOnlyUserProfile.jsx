import React from "react";
import { UserProfile } from "@/components/proptypes";
import UserAvatar from "@/components/UserAvatar";
import UserGroups from "@/components/UserGroups";

import UserAccess from "./UserAccess";
import useUserGroups from "../hooks/useUserGroups";

export default function ReadOnlyUserProfile({ user }) {
  const { groups, isLoading: isLoadingGroups } = useUserGroups(user);

  return (
    <div className="col-md-4 col-md-offset-4 profile__container">
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
      <dl className="profile__dl">
        <dt>Name:</dt>
        <dd>{user.name}</dd>
        <dt>Email:</dt>
        <dd>{user.email}</dd>
        <dt className="m-b-5">Groups:</dt>
        <dd>{isLoadingGroups ? "Loading..." : <UserGroups groups={groups} />}</dd>
      </dl>
      <UserAccess user={user} />
    </div>
  );
}

ReadOnlyUserProfile.propTypes = {
  user: UserProfile.isRequired,
};
